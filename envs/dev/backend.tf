terraform {
  required_version = ">= 1.6.0"
  backend "s3" {
    bucket         = "tf-state-platform-4239cd7f" # Use your bootstrap S3 bucket name here
    key            = "envs/dev/terraform.tfstate"
    region         = "us-east-1"
    dynamodb_table = "tf-state-locks-platform"
  }
}