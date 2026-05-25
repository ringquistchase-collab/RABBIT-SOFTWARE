variable "env" {
  description = "Deployment environment"
  type        = string
  default     = "prod"
  validation {
    condition     = contains(["dev", "staging", "prod"], var.env)
    error_message = "env must be dev, staging, or prod."
  }
}

variable "region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}

variable "cluster_name" {
  description = "EKS cluster name"
  type        = string
  default     = "rabbitos-enterprise"
}

variable "kubernetes_version" {
  description = "EKS Kubernetes version"
  type        = string
  default     = "1.29"
}

variable "vpc_cidr" {
  description = "VPC CIDR block"
  type        = string
  default     = "10.0.0.0/16"
}

variable "availability_zones" {
  description = "AZs to deploy into"
  type        = list(string)
  default     = ["us-east-1a", "us-east-1b", "us-east-1c"]
}

variable "node_instance_types" {
  description = "On-demand node instance types"
  type        = list(string)
  default     = ["m5.xlarge", "m5.2xlarge"]
}

variable "gpu_instance_types" {
  description = "GPU node instance types for LLM inference"
  type        = list(string)
  default     = ["g4dn.xlarge", "g4dn.2xlarge"]
}

variable "on_demand_desired" { type = number; default = 2 }
variable "on_demand_min"     { type = number; default = 1 }
variable "on_demand_max"     { type = number; default = 10 }

variable "gpu_desired"       { type = number; default = 1 }
variable "gpu_min"           { type = number; default = 0 }
variable "gpu_max"           { type = number; default = 4 }

variable "tags" {
  description = "Common resource tags"
  type        = map(string)
  default     = {}
}
