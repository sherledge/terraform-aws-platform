variable "environment" { type = string }
variable "vpc_id" { type = string }
variable "private_subnet_ids" { type = list(string) }
variable "db_sg_id" { type = string }
variable "multi_az" { type = bool }