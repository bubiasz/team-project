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
import matplotlib
from fastapi import FastAPI, HTTPException, UploadFile, Request
from starlette.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from urllib.parse import urlparse
from facade import ModelFacade

from utils import check_bird


app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

base = os.getcwd()

model = ModelFacade()
model.load_model(os.path.join(base, "models"), "100push0.7413.pth")


"""""
load_dotenv()
s3_client = boto3.client(
    "s3",
    aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
    aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
)
aws_bucket_name = os.getenv("AWS_BUCKET_NAME")


def s3_upload_file(local_path, amazon_path):
    
    # Function to upload a file to an S3 bucket
    
    try:
        s3_client.upload_file(local_path, aws_bucket_name, amazon_path)
        return f"https://{aws_bucket_name}.s3.amazonaws.com/{amazon_path}"
    except FileNotFoundError:
        return "Upload failed file not found"
    except exceptions.NoCredentialsError:
        return "Credentials not provided"
"""


class Response(BaseModel):
    predictions: dict[int, tuple]
    original_img_url: str
    scaled_img_url: str
    activation_urls: list[str]


app.mount("/static", StaticFiles(directory="static"), name="static")


@app.post("/heatmap_picker")
async def heatmap_picker(request: Request):
    data = await request.json()
    images = data.get("images")

    def extract_number_from_url(url: str) -> int:
        parts = url.split("/")
        filename = parts[-1]
        number = filename.split(".")[0]
        return int(number)

    def extract_folder_name(url: str) -> str:
        parsed_url = urlparse(url)
        path_parts = [part for part in parsed_url.path.split("/") if part]
        folder_name = path_parts[-3]
        return folder_name

    if images:
        selected_numbers = [extract_number_from_url(image) for image in images]
        folder_name = extract_folder_name(images[0])

        dir_path = os.path.join(base, "static", "requests", folder_name)

        os.makedirs(os.path.join(dir_path, "selected"))

        for number in selected_numbers:
            img_path = os.path.join(dir_path, "activations", f"{number}.jpg")
            shutil.copy(
                os.path.join(img_path),
                os.path.join(dir_path, "selected"),
            )

        return {"Selected numbers": selected_numbers}
    else:
        return {"message": "No images provided"}


@app.post("/upload", response_model=Response)
async def upload(photo: UploadFile):
    """
    Uploads a photo and returns predicted species with corresponding confidence.
    """

    dir_name = "".join(
        secrets.choice(string.ascii_letters + string.digits) for _ in range(22)
    ) + str(int(time.time()))

    dir_path = os.path.join(base, "static", "requests", dir_name)
    os.makedirs(dir_path)

    img_path = os.path.join(dir_path, "upload.jpg")

    with open(img_path, "wb") as buffer:
        buffer.write(await photo.read())

    try:
        img_tens = model.load_image(img_path)
        img_tens = img_tens.cuda()
    except FileNotFoundError:
        shutil.rmtree(os.path.join(dir_path))
        raise HTTPException(staus_code=404, detail="Image file not found.")

    if not check_bird(img_path):
        raise HTTPException(status_code=403, detail="Not a bird image.")

    predictions, img_original, prot_act, prot_act_pattern = model.predict(img_tens)
    plt.imsave(os.path.join(dir_path, "scaled.jpg"), img_original)

    os.makedirs(os.path.join(dir_path, "activations"))
    activations = model.nearest_k_prototypes(
        10, img_original, prot_act, prot_act_pattern
    )

    for i, img in enumerate(activations):
        plt.imsave(os.path.join(dir_path, "activations", f"{i}.jpg"), img)

    """
    For online version

    original_img_url = s3_upload_file(
        os.path.join(dir_path, "upload.jpg"), os.path.join(dir_name, "upload.jpg")
    )

    scaled_img_url = s3_upload_file(
        os.path.join(dir_path, "scaled.jpg"), os.path.join(dir_name, "scaled.jpg")
    )

    activation_urls = [
        s3_upload_file(
            os.path.join(dir_path, "activations", f"{i}.jpg"),
            os.path.join(dir_name, "activations", f"{i}.jpg"),
        )
        for i in range(10)
    ]
    """

    return Response(
        predictions=predictions,
        original_img_url=os.path.join(
            "http://127.0.0.1:8000/static/", "requests", dir_name, "upload.jpg"
        ),
        scaled_img_url=os.path.join(
            "http://127.0.0.1:8000/static/", "requests", dir_name, "scaled.jpg"
        ),
        activation_urls=[
            os.path.join(
                "http://127.0.0.1:8000/static/",
                "requests",
                dir_name,
                "activations",
                f"{i}.jpg",
            )
            for i in range(10)
        ],
    )

    """
    return Response(
        predictions=predictions,
        original_img_url=original_img_url,
        scaled_img_url=scaled_img_url,
        activation_urls=activation_urls,
    )
    """
