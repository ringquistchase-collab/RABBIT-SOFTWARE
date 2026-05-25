module "eks" {
  source  = "terraform-aws-modules/eks/aws"
  version = "~> 20.0"

  cluster_name    = local.name
  cluster_version = var.kubernetes_version

  vpc_id                         = module.vpc.vpc_id
  subnet_ids                     = module.vpc.private_subnet_ids
  cluster_endpoint_public_access = true

  # IRSA
  enable_irsa = true

  # Managed node groups
  eks_managed_node_groups = {
    # General-purpose on-demand nodes
    general = {
      name           = "general-${var.env}"
      instance_types = var.node_instance_types
      ami_type       = "AL2_x86_64"
      capacity_type  = "ON_DEMAND"

      min_size     = var.on_demand_min
      max_size     = var.on_demand_max
      desired_size = var.on_demand_desired

      labels = { role = "general" }
      taints = []
    }

    # GPU nodes for LLM inference
    gpu = {
      name           = "gpu-${var.env}"
      instance_types = var.gpu_instance_types
      ami_type       = "AL2_x86_64_GPU"
      capacity_type  = "SPOT"

      min_size     = var.gpu_min
      max_size     = var.gpu_max
      desired_size = var.gpu_desired

      labels = { role = "gpu", "nvidia.com/gpu" = "true" }
      taints = [{
        key    = "nvidia.com/gpu"
        value  = "true"
        effect = "NO_SCHEDULE"
      }]
    }
  }

  # Add-ons
  cluster_addons = {
    coredns            = { most_recent = true }
    kube-proxy         = { most_recent = true }
    vpc-cni            = { most_recent = true }
    aws-ebs-csi-driver = { most_recent = true }
  }

  # Cluster access
  enable_cluster_creator_admin_permissions = true
}
