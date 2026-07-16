terraform {
  required_version = ">= 1.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = var.project_name
      Environment = var.environment
      ManagedBy   = "terraform"
    }
  }
}

locals {
  namespace       = "${var.project_name}/${var.environment}"
  sample_app_name = "${var.project_name}-sample-app-${var.environment}"
  slack_bot_name  = "${var.project_name}-slack-notifier-${var.environment}"
}

# ---------------------------------------------------------------------------
# Sample application Lambda
# ---------------------------------------------------------------------------

resource "aws_iam_role" "sample_app" {
  name = "${local.sample_app_name}-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "lambda.amazonaws.com"
      }
    }]
  })
}

resource "aws_iam_role_policy_attachment" "sample_app_basic" {
  role       = aws_iam_role.sample_app.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_cloudwatch_log_group" "sample_app" {
  name              = "/aws/lambda/${local.sample_app_name}"
  retention_in_days = var.log_retention_days
}

resource "aws_lambda_function" "sample_app" {
  function_name = local.sample_app_name
  role          = aws_iam_role.sample_app.arn
  handler       = "lambda_function.lambda_handler"
  runtime       = "python3.11"
  filename      = "packages/sample_app.zip"

  source_code_hash = filebase64sha256("packages/sample_app.zip")

  depends_on = [aws_cloudwatch_log_group.sample_app]
}

# ---------------------------------------------------------------------------
# Metric filter & alarm for ERROR logs
# ---------------------------------------------------------------------------

resource "aws_cloudwatch_log_metric_filter" "errors" {
  name           = "${var.project_name}-error-count-${var.environment}"
  pattern        = "{ $.level = \"ERROR\" }"
  log_group_name = aws_cloudwatch_log_group.sample_app.name

  metric_transformation {
    name          = "ErrorCount"
    namespace     = local.namespace
    value         = "1"
    default_value = "0"
    unit          = "Count"
  }
}

resource "aws_cloudwatch_metric_alarm" "high_error_rate" {
  alarm_name          = "${var.project_name}-high-error-rate-${var.environment}"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = aws_cloudwatch_log_metric_filter.errors.metric_transformation[0].name
  namespace           = aws_cloudwatch_log_metric_filter.errors.metric_transformation[0].namespace
  period              = var.error_period
  statistic           = "Sum"
  threshold           = var.error_threshold
  alarm_description   = "Triggers when ERROR logs exceed ${var.error_threshold} in ${var.error_period} seconds"
  alarm_actions       = [aws_sns_topic.alerts.arn]
  ok_actions          = [aws_sns_topic.alerts.arn]
  treat_missing_data  = "notBreaching"
}

# ---------------------------------------------------------------------------
# SNS notifications: email + Slack via Lambda
# ---------------------------------------------------------------------------

resource "aws_sns_topic" "alerts" {
  name              = "${var.project_name}-alerts-${var.environment}"
  display_name      = "Cloud Log Monitoring Alerts"
  kms_master_key_id = "alias/aws/sns"
}

resource "aws_sns_topic_subscription" "email" {
  topic_arn = aws_sns_topic.alerts.arn
  protocol  = "email"
  endpoint  = var.alert_email
}

resource "aws_iam_role" "slack_notifier" {
  name = "${local.slack_bot_name}-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "lambda.amazonaws.com"
      }
    }]
  })
}

resource "aws_iam_role_policy_attachment" "slack_notifier_basic" {
  role       = aws_iam_role.slack_notifier.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_lambda_function" "slack_notifier" {
  function_name = local.slack_bot_name
  role          = aws_iam_role.slack_notifier.arn
  handler       = "lambda_function.lambda_handler"
  runtime       = "python3.11"
  filename      = "packages/slack_notifier.zip"

  source_code_hash = filebase64sha256("packages/slack_notifier.zip")

  environment {
    variables = {
      SLACK_WEBHOOK_URL = var.slack_webhook_url
    }
  }
}

# Slack subscription is disabled for email-only alerts.
# To enable Slack notifications later, uncomment the resources below and
# set a valid slack_webhook_url in terraform.tfvars.
#
# resource "aws_lambda_permission" "sns_invoke_slack" {
#   statement_id  = "AllowExecutionFromSNS"
#   action        = "lambda:InvokeFunction"
#   function_name = aws_lambda_function.slack_notifier.function_name
#   principal     = "sns.amazonaws.com"
#   source_arn    = aws_sns_topic.alerts.arn
# }
#
# resource "aws_sns_topic_subscription" "slack" {
#   topic_arn = aws_sns_topic.alerts.arn
#   protocol  = "lambda"
#   endpoint  = aws_lambda_function.slack_notifier.arn
#
#   depends_on = [aws_lambda_permission.sns_invoke_slack]
# }

# ---------------------------------------------------------------------------
# CloudWatch Dashboard
# ---------------------------------------------------------------------------

resource "aws_cloudwatch_dashboard" "main" {
  dashboard_name = "${var.project_name}-${var.environment}"

  dashboard_body = jsonencode({
    widgets = [
      {
        type   = "metric"
        x      = 0
        y      = 0
        width  = 12
        height = 6
        properties = {
          title  = "Error Count"
          region = var.aws_region
          metrics = [
            [local.namespace, "ErrorCount"]
          ]
          period = var.error_period
          stat   = "Sum"
        }
      },
      {
        type   = "log"
        x      = 12
        y      = 0
        width  = 12
        height = 6
        properties = {
          title         = "Recent ERROR Logs"
          region        = var.aws_region
          query         = "SOURCE '/aws/lambda/${local.sample_app_name}' | fields @timestamp, @message\n| filter @message like \"ERROR\"\n| sort @timestamp desc\n| limit 20"
          logGroupNames = ["/aws/lambda/${local.sample_app_name}"]
        }
      },
      {
        type   = "metric"
        x      = 0
        y      = 6
        width  = 12
        height = 6
        properties = {
          title  = "Lambda Invocations"
          region = var.aws_region
          metrics = [
            ["AWS/Lambda", "Invocations", "FunctionName", local.sample_app_name]
          ]
          period = 60
          stat   = "Sum"
        }
      },
      {
        type   = "metric"
        x      = 12
        y      = 6
        width  = 12
        height = 6
        properties = {
          title  = "Lambda Errors"
          region = var.aws_region
          metrics = [
            ["AWS/Lambda", "Errors", "FunctionName", local.sample_app_name]
          ]
          period = 60
          stat   = "Sum"
        }
      }
    ]
  })
}
