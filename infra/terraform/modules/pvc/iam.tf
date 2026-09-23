# IAM: least privilege per workload, plus the GitHub OIDC role used by CD (PVC-133).
#
#   execution role (per workload)  pull the image, write its own log group, read only its own secrets
#   task role (mcp, api, worker)   read/write evidence under evidence/ with the data key; no delete, no
#                                  governance bypass (offboarding is an operator action, PVC-144)
#   migrate, bootstrap             no task role: they only talk to PostgreSQL
#   deploy role                    assumable only from this repository's GitHub environment

data "aws_iam_policy_document" "ecs_execution_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

# Task roles additionally pin the calling account and ECS resources (confused-deputy protection).
data "aws_iam_policy_document" "ecs_tasks_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [local.account_id]
    }
    condition {
      test     = "ArnLike"
      variable = "aws:SourceArn"
      values   = ["arn:${local.partition}:ecs:${local.region}:${local.account_id}:*"]
    }
  }
}

locals {
  # Secret ARNs without the ":json-key::" suffix used for the RDS-managed master secret.
  workload_secret_arns = {
    for k, w in local.workloads : k => distinct([
      for ref in values(w.secrets) : regex("^(arn:[^:]+:secretsmanager:[^:]+:[^:]+:secret:[^:]+)", ref)[0]
    ])
  }
  evidence_workloads = toset([for k, w in local.workloads : k if w.evidence])
}

# ---- Execution roles --------------------------------------------------------------------------------------
resource "aws_iam_role" "execution" {
  for_each           = local.workloads
  name               = "${local.prefix}-${each.key}-execution"
  assume_role_policy = data.aws_iam_policy_document.ecs_execution_assume.json
  tags               = local.tags
}

data "aws_iam_policy_document" "execution" {
  for_each = local.workloads

  statement {
    sid       = "EcrAuth"
    actions   = ["ecr:GetAuthorizationToken"]
    resources = ["*"]
  }

  statement {
    sid = "EcrPull"
    actions = [
      "ecr:BatchCheckLayerAvailability",
      "ecr:BatchGetImage",
      "ecr:GetDownloadUrlForLayer",
    ]
    resources = [aws_ecr_repository.this.arn]
  }

  statement {
    sid       = "Logs"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${aws_cloudwatch_log_group.workload[each.key].arn}:*"]
  }

  statement {
    sid       = "ReadOwnSecrets"
    actions   = ["secretsmanager:GetSecretValue"]
    resources = local.workload_secret_arns[each.key]
  }

  statement {
    sid       = "DecryptSecrets"
    actions   = ["kms:Decrypt"]
    resources = [aws_kms_key.data.arn]
    condition {
      test     = "StringEquals"
      variable = "kms:ViaService"
      values   = ["secretsmanager.${local.region}.amazonaws.com"]
    }
  }
}

resource "aws_iam_role_policy" "execution" {
  for_each = local.workloads
  name     = "execution"
  role     = aws_iam_role.execution[each.key].id
  policy   = data.aws_iam_policy_document.execution[each.key].json
}

# ---- Task roles -------------------------------------------------------------------------------------------
resource "aws_iam_role" "task" {
  for_each           = local.evidence_workloads
  name               = "${local.prefix}-${each.key}-task"
  assume_role_policy = data.aws_iam_policy_document.ecs_tasks_assume.json
  tags               = local.tags
}

data "aws_iam_policy_document" "task_evidence" {
  statement {
    sid       = "ListEvidencePrefix"
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.evidence.arn]
    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values   = ["${local.evidence_prefix}/*"]
    }
  }

  # Originals are immutable (Object Lock); there is deliberately no Delete* or BypassGovernanceRetention.
  statement {
    sid       = "ReadWriteEvidence"
    actions   = ["s3:GetObject", "s3:PutObject"]
    resources = ["${aws_s3_bucket.evidence.arn}/${local.evidence_prefix}/*"]
  }

  statement {
    sid       = "EvidenceKey"
    actions   = ["kms:Decrypt", "kms:GenerateDataKey"]
    resources = [aws_kms_key.data.arn]
    condition {
      test     = "StringEquals"
      variable = "kms:ViaService"
      values   = ["s3.${local.region}.amazonaws.com"]
    }
  }
}

resource "aws_iam_role_policy" "task_evidence" {
  for_each = local.evidence_workloads
  name     = "evidence"
  role     = aws_iam_role.task[each.key].id
  policy   = data.aws_iam_policy_document.task_evidence.json
}

# ---- GitHub Actions OIDC deploy role ----------------------------------------------------------------------
resource "aws_iam_openid_connect_provider" "github" {
  count          = var.create_github_oidc_provider ? 1 : 0
  url            = "https://token.actions.githubusercontent.com"
  client_id_list = ["sts.amazonaws.com"]
  tags           = local.tags
}

locals {
  github_oidc_provider_arn = var.create_github_oidc_provider ? aws_iam_openid_connect_provider.github[0].arn : var.github_oidc_provider_arn
}

data "aws_iam_policy_document" "deploy_assume" {
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]
    principals {
      type        = "Federated"
      identifiers = [local.github_oidc_provider_arn]
    }
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }
    # Only jobs bound to this repository's GitHub environment (with its protection rules) may deploy.
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:sub"
      values   = ["repo:${var.github_repository}:environment:${var.github_environment}"]
    }
  }
}

resource "aws_iam_role" "deploy" {
  name                 = "${local.prefix}-github-deploy"
  description          = "Assumed by GitHub Actions (${var.github_repository}, environment ${var.github_environment}) to deploy"
  assume_role_policy   = data.aws_iam_policy_document.deploy_assume.json
  max_session_duration = 3600
  tags                 = local.tags

  lifecycle {
    precondition {
      condition     = local.github_oidc_provider_arn != null
      error_message = "Set github_oidc_provider_arn when create_github_oidc_provider is false."
    }
  }
}

data "aws_iam_policy_document" "deploy" {
  statement {
    sid       = "EcrAuth"
    actions   = ["ecr:GetAuthorizationToken"]
    resources = ["*"]
  }

  statement {
    sid = "EcrPush"
    actions = [
      "ecr:BatchCheckLayerAvailability",
      "ecr:BatchGetImage",
      "ecr:CompleteLayerUpload",
      "ecr:DescribeImages",
      "ecr:DescribeImageScanFindings",
      "ecr:GetDownloadUrlForLayer",
      "ecr:InitiateLayerUpload",
      "ecr:PutImage",
      "ecr:UploadLayerPart",
    ]
    resources = [aws_ecr_repository.this.arn]
  }

  # RegisterTaskDefinition and Describe* do not support resource-level permissions.
  statement {
    sid = "EcsTaskDefinitions"
    actions = [
      "ecs:DescribeTaskDefinition",
      "ecs:RegisterTaskDefinition",
    ]
    resources = ["*"]
  }

  statement {
    sid       = "EcsServices"
    actions   = ["ecs:DescribeServices", "ecs:UpdateService"]
    resources = [for s in local.services : "arn:${local.partition}:ecs:${local.region}:${local.account_id}:service/${aws_ecs_cluster.this.name}/${s}"]
  }

  statement {
    sid     = "EcsRunOneOffTasks"
    actions = ["ecs:RunTask"]
    resources = [
      for k in ["migrate", "bootstrap"] : "arn:${local.partition}:ecs:${local.region}:${local.account_id}:task-definition/${local.prefix}-${k}:*"
    ]
    condition {
      test     = "ArnEquals"
      variable = "ecs:cluster"
      values   = [aws_ecs_cluster.this.arn]
    }
  }

  statement {
    sid       = "EcsTasks"
    actions   = ["ecs:DescribeTasks", "ecs:ListTasks"]
    resources = ["*"]
    condition {
      test     = "ArnEquals"
      variable = "ecs:cluster"
      values   = [aws_ecs_cluster.this.arn]
    }
  }

  # deploy.sh looks up the one-off task's security group by name (read-only, no resource-level support).
  statement {
    sid       = "DescribeSecurityGroups"
    actions   = ["ec2:DescribeSecurityGroups"]
    resources = ["*"]
  }

  statement {
    sid       = "PassTaskRoles"
    actions   = ["iam:PassRole"]
    resources = concat(values(aws_iam_role.execution)[*].arn, values(aws_iam_role.task)[*].arn)
    condition {
      test     = "StringEquals"
      variable = "iam:PassedToService"
      values   = ["ecs-tasks.amazonaws.com"]
    }
  }

  statement {
    sid       = "ReadOneOffTaskLogs"
    actions   = ["logs:GetLogEvents", "logs:FilterLogEvents"]
    resources = [for k in ["migrate", "bootstrap"] : "${aws_cloudwatch_log_group.workload[k].arn}:*"]
  }
}

resource "aws_iam_role_policy" "deploy" {
  name   = "deploy"
  role   = aws_iam_role.deploy.id
  policy = data.aws_iam_policy_document.deploy.json
}
