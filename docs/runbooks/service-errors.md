# Elevated 5xx errors (availability burn)

1. Dashboard "HTTP 5xx ratio" by service (`mcp`, `api`). Check the latest deploy (CD pipeline run) and ECS task health.
2. If errors started with a deploy, roll back by redeploying the previous image tag through the CD workflow. Migrations are additive; a rollback does not need a down-migration unless the release notes say so.
3. Database-related errors (connection failures, pool exhaustion): check RDS metrics. Each process uses a pool of up to 10 connections.
4. Authentication-related errors (JWKS fetch failures): check the identity provider's status and that its host is on the egress allow-list.
5. Hold a post-incident review if the fast-burn alert fired.
