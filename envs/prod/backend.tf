terraform {
  required_version = ">= 1.6.0"
  backend "s3" {
    bucket         = "tf-state-platform-4239cd7f"
    key            = "envs/prod/terraform.tfstate"
    region         = "us-east-1"
    dynamodb_table = "tf-state-locks-platform"
  }
}
