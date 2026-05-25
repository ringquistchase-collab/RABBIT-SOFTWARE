output "cluster_name"     { value = module.eks.cluster_name }
output "cluster_endpoint" { value = module.eks.cluster_endpoint }
output "cluster_ca"       { value = module.eks.cluster_ca; sensitive = true }
output "oidc_provider_arn"{ value = module.eks.oidc_provider_arn }
output "vpc_id"           { value = module.vpc.vpc_id }
output "private_subnets"  { value = module.vpc.private_subnets }
output "public_subnets"   { value = module.vpc.public_subnets }
output "cold_storage_bucket" { value = aws_s3_bucket.cold_storage.bucket }
output "gateway_role_arn" { value = module.gateway_irsa.iam_role_arn }
output "worker_role_arn"  { value = module.worker_irsa.iam_role_arn }
