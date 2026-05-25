module "vpc" {
  source  = "terraform-aws-modules/vpc/aws"
  version = "~> 5.4"

  name = "${local.name}-vpc"
  cidr = var.vpc_cidr

  azs             = var.availability_zones
  private_subnets = [for i, az in var.availability_zones : cidrsubnet(var.vpc_cidr, 4, i)]
  public_subnets  = [for i, az in var.availability_zones : cidrsubnet(var.vpc_cidr, 4, i + 10)]

  enable_nat_gateway     = true
  single_nat_gateway     = var.env != "prod"
  enable_dns_hostnames   = true
  enable_dns_support     = true

  # EKS subnet tags
  private_subnet_tags = {
    "kubernetes.io/role/internal-elb"                     = "1"
    "kubernetes.io/cluster/${local.name}"                 = "owned"
  }
  public_subnet_tags = {
    "kubernetes.io/role/elb"                              = "1"
    "kubernetes.io/cluster/${local.name}"                 = "owned"
  }
}
