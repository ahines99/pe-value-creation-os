terraform {
  # 1.11+: ephemeral resources and write-only attributes keep generated database passwords out of state.
  required_version = ">= 1.11.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 6.0, < 7.0"
    }
    random = {
      source  = "hashicorp/random"
      version = ">= 3.7, < 4.0"
    }
  }
}
