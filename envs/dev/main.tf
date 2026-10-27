provider "aws" {
  region = "us-east-1"
}

module "vpc" {
  source      = "../../modules/vpc"
  environment = "dev"
  vpc_cidr    = "10.10.0.0/16"
}

module "security_groups" {
  source      = "../../modules/security-groups"
  environment = "dev"
  vpc_id      = module.vpc.vpc_id
}

module "iam" {
  source      = "../../modules/iam"
  environment = "dev"
}

module "alb" {
  source            = "../../modules/alb"
  environment       = "dev"
  vpc_id            = module.vpc.vpc_id
  public_subnet_ids = module.vpc.public_subnet_ids
  alb_sg_id         = module.security_groups.alb_sg_id
}

module "compute" {
  source                = "../../modules/compute"
  environment           = "dev"
  vpc_id                = module.vpc.vpc_id
  private_subnet_ids    = module.vpc.private_subnet_ids
  app_sg_id             = module.security_groups.app_sg_id
  target_group_arn      = module.alb.target_group_arn
  instance_type         = "t3.micro"
  min_size              = 1
  max_size              = 2
  desired_capacity      = 1
  instance_profile_name = module.iam.instance_profile_name
}

module "rds" {
  source             = "../../modules/rds"
  environment        = "dev"
  vpc_id             = module.vpc.vpc_id
  private_subnet_ids = module.vpc.private_subnet_ids
  db_sg_id           = module.security_groups.db_sg_id
  multi_az           = false
}

output "alb_dns_name" {
  value = module.alb.dns_name
}