variable "project_name" {
  description = "Name used as a prefix for AWS resources"
  type        = string
  default     = "cloud-log-monitor"
}

variable "environment" {
  description = "Deployment environment (e.g., dev, staging, prod)"
  type        = string
  default     = "dev"
}

variable "aws_region" {
  description = "AWS region for deployment"
  type        = string
  default     = "us-east-1"
}

variable "alert_email" {
  description = "Email address to receive CloudWatch alarm notifications"
  type        = string
}

variable "slack_webhook_url" {
  description = "Slack incoming webhook URL for alarm notifications"
  type        = string
  sensitive   = true
}

variable "error_threshold" {
  description = "Number of ERROR log entries that trigger the alarm in the evaluation period"
  type        = number
  default     = 5
}

variable "error_period" {
  description = "Evaluation period in seconds for the error alarm"
  type        = number
  default     = 300
}

variable "log_retention_days" {
  description = "CloudWatch log group retention in days"
  type        = number
  default     = 14
}
