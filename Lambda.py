import json
import os
import boto3
import logging
from botocore.exceptions import ClientError
from typing import Dict, Any

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

class NotificationService:
    def __init__(self):
        self.sns = boto3.client('sns')
        self.email_topic_arn = os.environ['EMAIL_TOPIC_ARN']
        
    def validate_request(self, body: Dict[str, Any]) -> tuple:
        """Validate the incoming request body"""
        if not isinstance(body, dict):
            return False, "Invalid request format"
            
        required_fields = {
            'message': str,
            'type': str
        }
        
        for field, field_type in required_fields.items():
            if field not in body:
                return False, f"Missing required field: {field}"
            if not isinstance(body[field], field_type):
                return False, f"Invalid type for field: {field}"
                
        return True, ""

    def send_sms(self, phone_number: str, message: str) -> Dict:
        """Send SMS notification"""
        if not phone_number.startswith('+'):
            raise ValueError("Phone number must include country code starting with '+'")

        return self.sns.publish(
            PhoneNumber=phone_number,
            Message=message,
            MessageAttributes={
                'AWS.SNS.SMS.SMSType': {
                    'DataType': 'String',
                    'StringValue': 'Transactional'
                }
            }
        )

    def send_email(self, email: str, subject: str, message: str) -> Dict:
        """Send email notification"""
        # Validate email format (basic check)
        if '@' not in email or '.' not in email:
            raise ValueError("Invalid email format")

        # Subscribe the email to the topic
        subscription = self.sns.subscribe(
            TopicArn=self.email_topic_arn,
            Protocol='email',
            Endpoint=email,
            Attributes={
                'FilterPolicy': json.dumps({'email': [email]})
            }
        )

        # Publish the message
        return self.sns.publish(
            TopicArn=self.email_topic_arn,
            Message=message,
            Subject=subject,
            MessageAttributes={
                'email': {
                    'DataType': 'String',
                    'StringValue': email
                }
            }
        )

    def send_push(self, endpoint_arn: str, title: str, message: str) -> Dict:
        """Send push notification"""
        push_message = {
            'default': message,
            'APNS': json.dumps({
                'aps': {
                    'alert': {
                        'title': title,
                        'body': message
                    },
                    'sound': 'default',
                    'badge': 1
                }
            }),
            'FCM': json.dumps({
                'notification': {
                    'title': title,
                    'body': message
                },
                'priority': 'high'
            })
        }

        return self.sns.publish(
            TargetArn=endpoint_arn,
            Message=json.dumps(push_message),
            MessageStructure='json'
        )

def lambda_handler(event, context):
    """Main Lambda handler"""
    logger.info(f"Received event: {json.dumps(event)}")
    
    notification_service = NotificationService()
    
    try:
        # Verify HTTP method
        if event['httpMethod'] != 'POST':
            return {
                'statusCode': 405,
                'headers': {
                    'Content-Type': 'application/json',
                    'Strict-Transport-Security': 'max-age=31536000; includeSubDomains'
                },
                'body': json.dumps({'error': 'Method not allowed'})
            }

        # Parse and validate request body
        try:
            body = json.loads(event.get('body', '{}'))
        except json.JSONDecodeError:
            return {
                'statusCode': 400,
                'headers': {
                    'Content-Type': 'application/json',
                    'Strict-Transport-Security': 'max-age=31536000; includeSubDomains'
                },
                'body': json.dumps({'error': 'Invalid JSON in request body'})
            }

        # Validate request
        is_valid, error_message = notification_service.validate_request(body)
        if not is_valid:
            return {
                'statusCode': 400,
                'headers': {
                    'Content-Type': 'application/json',
                    'Strict-Transport-Security': 'max-age=31536000; includeSubDomains'
                },
                'body': json.dumps({'error': error_message})
            }

        notification_type = body['type'].lower()
        message = body['message']
        response = None

        if notification_type == 'sms':
            phone_number = body.get('phone_number')
            if not phone_number:
                raise ValueError("Phone number is required for SMS notifications")
            response = notification_service.send_sms(phone_number, message)

        elif notification_type == 'email':
            email = body.get('email')
            subject = body.get('subject', 'Notification')
            if not email:
                raise ValueError("Email address is required for email notifications")
            response = notification_service.send_email(email, subject, message)

        elif notification_type == 'push':
            endpoint_arn = body.get('endpoint_arn')
            title = body.get('title', 'Notification')
            if not endpoint_arn:
                raise ValueError("Endpoint ARN is required for push notifications")
            response = notification_service.send_push(endpoint_arn, title, message)

        else:
            return {
                'statusCode': 400,
                'headers': {
                    'Content-Type': 'application/json',
                    'Strict-Transport-Security': 'max-age=31536000; includeSubDomains'
                },
                'body': json.dumps({'error': 'Invalid notification type'})
            }

        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json',
                'Strict-Transport-Security': 'max-age=31536000; includeSubDomains'
            },
            'body': json.dumps({
                'message': 'Notification sent successfully',
                'messageId': response['MessageId']
            })
        }

    except ValueError as e:
        logger.error(f"Validation error: {str(e)}")
        return {
            'statusCode': 400,
            'headers': {
                'Content-Type': 'application/json',
                'Strict-Transport-Security': 'max-age=31536000; includeSubDomains'
            },
            'body': json.dumps({'error': str(e)})
        }

    except ClientError as e:
        logger.error(f"AWS error: {str(e)}")
        return {
            'statusCode': 500,
            'headers': {
                'Content-Type': 'application/json',
                'Strict-Transport-Security': 'max-age=31536000; includeSubDomains'
            },
            'body': json.dumps({'error': 'Internal server error'})
        }

    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        return {
            'statusCode': 500,
            'headers': {
                'Content-Type': 'application/json',
                'Strict-Transport-Security': 'max-age=31536000; includeSubDomains'
            },
            'body': json.dumps({'error': 'Internal server error'})
        }
