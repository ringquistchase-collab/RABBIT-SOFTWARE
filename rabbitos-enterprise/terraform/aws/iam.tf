# IRSA role for gateway service account
module "gateway_irsa" {
  source  = "terraform-aws-modules/iam/aws//modules/iam-role-for-service-accounts-eks"
  version = "~> 5.33"

  role_name = "${local.name}-gateway"

  oidc_providers = {
    main = {
      provider_arn               = module.eks.oidc_provider_arn
      namespace_service_accounts = ["rabbitos:rabbitos-gateway"]
    }
  }

  role_policy_arns = {
    s3     = "arn:aws:iam::aws:policy/AmazonS3ReadOnlyAccess"
    custom = aws_iam_policy.gateway_policy.arn
  }
}

resource "aws_iam_policy" "gateway_policy" {
  name = "${local.name}-gateway-policy"
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["secretsmanager:GetSecretValue"]
        Resource = ["arn:aws:secretsmanager:${var.region}:*:secret:rabbitos/*"]
      },
      {
        Effect   = "Allow"
        Action   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
        Resource = ["${aws_s3_bucket.cold_storage.arn}/*"]
      }
    ]
  })
}

# IRSA role for workers (needs Bedrock / S3 / Secrets)
module "worker_irsa" {
  source  = "terraform-aws-modules/iam/aws//modules/iam-role-for-service-accounts-eks"
  version = "~> 5.33"

  role_name = "${local.name}-worker"

  oidc_providers = {
    main = {
      provider_arn               = module.eks.oidc_provider_arn
      namespace_service_accounts = ["rabbitos:rabbitos-worker"]
    }
  }

  role_policy_arns = {
    s3      = "arn:aws:iam::aws:policy/AmazonS3FullAccess"
    bedrock = aws_iam_policy.bedrock_policy.arn
  }
}

resource "aws_iam_policy" "bedrock_policy" {
  name = "${local.name}-bedrock-policy"
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"]
      Resource = ["arn:aws:bedrock:${var.region}::foundation-model/*"]
    }]
  })
}
