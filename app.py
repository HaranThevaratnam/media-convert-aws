from flask import Flask, request, render_template
import boto3
import os

app = Flask(__name__)
UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

AWS_REGION = "eu-west-2"
S3_BUCKET = "your-s3-bucket-name"  # <-- Change this to your actual S3 bucket name

def upload_to_s3(local_filepath, bucket_name, s3_key):
    """
    Uploads a file to AWS S3.
    """
    s3_client = boto3.client("s3")
    s3_client.upload_file(
        local_filepath, bucket_name, s3_key, ExtraArgs={"ContentType": "video/mp4", "ACL": "public-read"}
    )
    return f"https://{bucket_name}.s3.{AWS_REGION}.amazonaws.com/{s3_key}"

@app.route("/", methods=["GET", "POST"])
def upload_file():
    """
    Handles video uploads and uploads them to S3.
    """
    if request.method == "POST":
        file = request.files["file"]
        if file:
            filename = file.filename.replace(" ", "_")
            local_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
            file.save(local_path)

            s3_key = f"uploads/{filename}"
            s3_url = upload_to_s3(local_path, S3_BUCKET, s3_key)

            return f"File uploaded! You can access it here: <a href='{s3_url}'>{s3_url}</a>"

    return '''
        <h1>Upload Video to S3</h1>
        <form method="post" enctype="multipart/form-data">
            <input type="file" name="file">
            <input type="submit" value="Upload">
        </form>
    '''

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0")
