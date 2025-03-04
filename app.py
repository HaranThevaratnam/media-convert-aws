from flask import Flask, request, render_template, redirect, url_for
import boto3
import os
import time

app = Flask(__name__)
UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

S3_BUCKET = "flashrevisionlab-prod"
OUTPUT_BUCKET = "flash-data-bucket"
OUTPUT_FOLDER = "media-convert-videos"

boto3.setup_default_session(region_name="eu-west-2")


def upload_to_s3(local_filepath, bucket_name, s3_key):
    """
    Uploads a local file to S3.
    :param local_filepath: str - Path to the local file
    :param bucket_name: str - Name of the S3 bucket
    :param s3_key: str - Key (path) in the S3 bucket
    :return: str - S3 URL of the uploaded file
    """
    s3_client = boto3.client("s3")
    s3_client.upload_file(
        local_filepath,
        bucket_name,
        s3_key,
        ExtraArgs={"ContentType": "video/mp4", "ACL": "public-read"}
    )
    return f"https://{bucket_name}.s3.eu-west-2.amazonaws.com/{s3_key}"


def set_s3_object_public(bucket_name, object_key):
    """
    Sets the ACL of an S3 object to public-read.
    :param bucket_name: str - S3 bucket name
    :param object_key: str - S3 object key
    """
    s3_client = boto3.client("s3")
    s3_client.put_object_acl(Bucket=bucket_name, Key=object_key, ACL="public-read")


def process_video_with_mediaconvert(input_s3_url, output_s3_folder, output_bucket):
    region = "eu-west-2"
    mediaconvert_client = boto3.client("mediaconvert", region_name=region)
    endpoints = mediaconvert_client.describe_endpoints()
    mediaconvert_endpoint = endpoints["Endpoints"][0]["Url"]
    mediaconvert_client = boto3.client(
        "mediaconvert", endpoint_url=mediaconvert_endpoint, region_name=region
    )

    input_filename = input_s3_url.split("/")[-1]
    output_filename = input_filename.replace(".mp4", "_converted.m3u8")
    output_s3_url = f"s3://{output_bucket}/{output_s3_folder}/playlist.m3u8"

    job_settings = {
        "Inputs": [
            {
                "FileInput": input_s3_url,
                "VideoSelector": {},
                "AudioSelectors": {"Audio Selector 1": {"DefaultSelection": "DEFAULT"}},
            }
        ],
        "OutputGroups": [
            {
                "Name": "HLS Group",
                "OutputGroupSettings": {
                    "Type": "HLS_GROUP_SETTINGS",
                    "HlsGroupSettings": {
                        "SegmentLength": 6,
                        "MinSegmentLength": 0,
                        "Destination": f"s3://{output_bucket}/{output_s3_folder}/"
                    }
                },
                "Outputs": [
                    {
                        "NameModifier": "_1080p",
                        "VideoDescription": {
                            "Width": 1920,
                            "Height": 1080,
                            "CodecSettings": {
                                "Codec": "H_264",
                                "H264Settings": {
                                    "Bitrate": 5000000,
                                    "CodecProfile": "HIGH",
                                    "CodecLevel": "AUTO",
                                    "RateControlMode": "CBR",
                                    "FramerateControl": "INITIALIZE_FROM_SOURCE",
                                    "FramerateConversionAlgorithm": "DUPLICATE_DROP",
                                    "GopSize": 90,
                                    "GopSizeUnits": "FRAMES"
                                }
                            }
                        },
                        "ContainerSettings": {
                            "Container": "M3U8"
                        },
                        "AudioDescriptions": [
                            {
                                "CodecSettings": {
                                    "Codec": "AAC",
                                    "AacSettings": {
                                        "Bitrate": 96000,
                                        "CodingMode": "CODING_MODE_2_0",
                                        "SampleRate": 48000
                                    }
                                }
                            }
                        ]
                    }
                ]
            }
        ],
        "TimecodeConfig": {
            "Source": "ZEROBASED"
        }
    }

    job = mediaconvert_client.create_job(
        Role="arn:aws:iam::109672096318:role/service-role/MediaConvert_Default_Role",
        Queue="arn:aws:mediaconvert:eu-west-2:109672096318:queues/Default",
        UserMetadata={"Customer": "FlashRevisionLab"},
        Settings=job_settings,
        AccelerationSettings={"Mode": "DISABLED"},
        StatusUpdateInterval="SECONDS_60",
        Priority=0
    )

    job_id = job["Job"]["Id"]
    print(f"MediaConvert job {job_id} submitted.")

    while True:
        job_status = mediaconvert_client.get_job(Id=job_id)
        status = job_status["Job"]["Status"]
        print(f"Job Status: {status}")
        if status in ["COMPLETE", "ERROR"]:
            break
        time.sleep(60)

    if status == "COMPLETE":
        print(f"MediaConvert job {job_id} completed successfully.")
        output_object_key = f"{output_s3_folder}/{os.path.splitext(os.path.basename(input_s3_url))[0]}_1080p.m3u8"
        set_s3_object_public(output_bucket, output_object_key)
        return f"https://{output_bucket}.s3.amazonaws.com/{output_object_key}"
    else:
        print(f"MediaConvert job {job_id} failed.")
        return None


@app.route("/", methods=["GET", "POST"])
def upload_file():
    if request.method == "POST":
        file = request.files["file"]
        if file:
            filepath = os.path.join(UPLOAD_FOLDER, file.filename)
            file.save(filepath)

            s3_key = f"Site_Main_Images/{file.filename.replace(' ', '_')}"
            s3_url = upload_to_s3(filepath, S3_BUCKET, s3_key)

            processed_url = process_video_with_mediaconvert(s3_url,
                                                            output_s3_folder="media-convert-videos",
                                                            output_bucket="flash-data-bucket"
                                                            )
            return render_template("index.html", processed_url=processed_url)

    return render_template("index.html", processed_url=None)


if __name__ == "__main__":
    app.run(debug=True)
