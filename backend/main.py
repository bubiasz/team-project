import os
import time
import shutil
import string
import secrets

import boto3
import botocore.exceptions as exceptions

from dotenv import load_dotenv
from pydantic import BaseModel
import matplotlib.pyplot as plt
from fastapi import FastAPI, HTTPException, UploadFile

from facade import ModelFacade


app = FastAPI()

base = os.getcwd()

model = ModelFacade()
model.load_model(os.path.join(base, "models"), "100push0.7413.pth")

load_dotenv()
s3_client = boto3.client(
    's3',
    aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
    aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
)
aws_bucket_name = os.getenv('AWS_BUCKET_NAME')


class Response(BaseModel):
    predictions: dict[int, tuple]
    original_img_url: str
    scaled_img_url: str
    activation_urls: list[str]


def s3_upload_file(local_path, amazon_path):
    """
    Function to upload a file to an S3 bucket
    """
    try:
        s3_client.upload_file(local_path, aws_bucket_name, amazon_path)
        return f"https://{aws_bucket_name}.s3.amazonaws.com/{amazon_path}"
    except FileNotFoundError:
        return "Upload failed file not found"
    except exceptions.NoCredentialsError:
        return "Credentials not provided"


@app.post("/upload", response_model=Response)
async def upload(photo: UploadFile):
    """
    Uploads a photo and returns predicted species with corresponding confidence.
    """
    dir_name = "".join(secrets.choice(
        string.ascii_letters + string.digits) for _ in range(22)) + str(int(time.time()))

    dir_path = os.path.join(base, "requests", dir_name)
    os.makedirs(dir_path)

    img_path = os.path.join(dir_path, "upload.jpg")
    with open(img_path, "wb") as buffer:
        buffer.write(await photo.read())
    
    try:
        img_tens = model.load_image(img_path)
    except FileNotFoundError:
        shutil.rmtree(os.path.join(dir_path))
        raise HTTPException(staus_code=404, detail="Image file not found.")

    predictions, img_original, prot_act, prot_act_pattern = model.predict(img_tens)
    plt.imsave(os.path.join(dir_path, "scaled.jpg"), img_original)
    
    os.makedirs(os.path.join(dir_path, "activations"))
    activations = model.nearest_k_prototypes(
        10, img_original, prot_act, prot_act_pattern)

    for i, img in enumerate(activations):
        plt.imsave(os.path.join(dir_path, "activations", f"{i}.jpg"), img)

    original_img_url = s3_upload_file(
        os.path.join(dir_path, "upload.jpg"), os.path.join(dir_name, "upload.jpg"))

    scaled_img_url = s3_upload_file(
        os.path.join(dir_path, "scaled.jpg"), os.path.join(dir_name, "scaled.jpg"))

    activation_urls = [
        s3_upload_file(
            os.path.join(dir_path, "activations", f"{i}.jpg"),
            os.path.join(dir_name, "activations", f"{i}.jpg")) for i in range(10)
    ]

    shutil.rmtree(os.path.join(dir_path))
   
    return Response(
        predictions=predictions,
        original_img_url=original_img_url,
        scaled_img_url=scaled_img_url,
        activation_urls=activation_urls
    )