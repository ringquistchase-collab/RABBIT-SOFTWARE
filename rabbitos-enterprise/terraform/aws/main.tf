terraform {
  required_version = ">= 1.6"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "~> 2.25"
    }
    helm = {
      source  = "hashicorp/helm"
      version = "~> 2.12"
    }
  }

  backend "s3" {
    # Configured via -backend-config in bootstrap.sh
    encrypt = true
  }
}

provider "aws" {
  region = var.region
  default_tags { tags = local.common_tags }
}

provider "kubernetes" {
  host                   = module.eks.cluster_endpoint
  cluster_ca_certificate = base64decode(module.eks.cluster_ca)
  token                  = data.aws_eks_cluster_auth.this.token
}

provider "helm" {
  kubernetes {
    host                   = module.eks.cluster_endpoint
    cluster_ca_certificate = base64decode(module.eks.cluster_ca)
    token                  = data.aws_eks_cluster_auth.this.token
  }
}

data "aws_caller_identity" "current" {}

data "aws_eks_cluster_auth" "this" {
  name = module.eks.cluster_name
}

locals {
  name        = "${var.cluster_name}-${var.env}"
  common_tags = merge(var.tags, {
    Project     = "rabbitos-enterprise"
    Environment = var.env
    ManagedBy   = "terraform"
  })
}

# S3 bucket for Terraform state (bootstrap only — pre-created)
resource "aws_s3_bucket" "cold_storage" {
  bucket = "rabbitos-cold-${data.aws_caller_identity.current.account_id}-${var.env}"
}

resource "aws_s3_bucket_versioning" "cold_storage" {
  bucket = aws_s3_bucket.cold_storage.id
  versioning_configuration { status = "Enabled" }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "cold_storage" {
  bucket = aws_s3_bucket.cold_storage.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}
