resource "aws_db_subnet_group" "main" {
  name       = "${var.environment}-db-subnet-group"
  subnet_ids = var.private_subnet_ids

  tags = { Name = "${var.environment}-db-subnet-group" }
}

resource "random_password" "db_password" {
  length  = 16
  special = false
}

resource "aws_secretsmanager_secret" "db_secret" {
  name = "${var.environment}-db-credentials-${random_password.db_password.result}" # Unique name context
}

resource "aws_secretsmanager_secret_version" "db_secret_val" {
  secret_id     = aws_secretsmanager_secret.db_secret.id
  secret_string = jsonencode({
    username = "postgres"
    password = random_password.db_password.result
  })
}

resource "aws_db_instance" "postgres" {
  identifier             = "${var.environment}-postgres"
  engine                 = "postgres"
  engine_version         = "15"
  instance_class         = "db.t3.micro"
  allocated_storage      = 20
  max_allocated_storage  = 100
  db_name                = "appdb"
  username               = "postgres"
  password               = random_password.db_password.result
  db_subnet_group_name   = aws_db_subnet_group.main.name
  vpc_security_group_ids = [var.db_sg_id]
  multi_az               = var.multi_az
  skip_final_snapshot    = true

  tags = { Name = "${var.environment}-postgres" }
}