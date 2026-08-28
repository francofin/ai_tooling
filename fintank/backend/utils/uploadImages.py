import boto3
import os
from dotenv import load_dotenv

load_dotenv()

session = boto3.Session(
    aws_access_key_id = os.getenv("AWS_ACCESS_KEY"),
    aws_secret_access_key = os.getenv("AWS_SECRET_ACESS_KEY"),
    region_name = os.getenv("AWS_REGION"),
)

class ImageUploader():
    def UploadImage(name,image):
        filename = name+'_picture.jpg'
        imagedata = image
        s3 = session.resource('s3')
    
        try:
            object = s3.Object(os.getenv("AWS_BUCKET_NAME"), filename)
            object.put(ACL='public-read',Body=imagedata,Key=filename)
            return True
        except Exception as e:
            return e