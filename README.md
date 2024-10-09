# Curtain Backend

## Description
Curtain Backend is the backend service for Curtain project which aims to provide a platform for data sharing and exploration of differential analysis data from Total proteomics and PTM proteomics analysis.

## Development Requirements
- Python 3.10 or higher
- Poetry for dependency management

### Main Dependencies
```shell
python = ">3.9,<3.13"
django = "^4.2.7"
djangorestframework = "^3.14.0"
django-filter = "^23.3"
djangorestframework-simplejwt = "^5.3.0"
drf-url-filters = "^0.5.1"
django-cors-headers = "^4.3.0"
pandas = "^2.1.2"
uniprotparser = "^1.1.0"
drf-flex-fields = "^1.0.2"
psycopg2 = "^2.9.9"
gunicorn = "^21.2.0"
dj-rest-auth = "^5.0.1"
django-dbbackup = "^4.0.2"
django-rest-auth = "^0.9.5"
django-request = "^1.6.3"
statsmodels = "^0.14.0"
channels = "^4.0.0"
uvicorn = {extras = ["standard"], version = "^0.24.0.post1"}
channels-redis = {extras = ["cryptography"], version = "^4.1.0"}
boto3 = "^1.28.82"
django-rq = "^2.8.1"
djangorestframework-api-key = "^3.0.0"
google-cloud-storage = "^2.13.0"
django-storages = {extras = ["s3"], version = "^1.14.2"} # For S3 storage backend,modify the extras to other storage backends as required
urllib3 = ">=1.25.4,<1.27"
django-extensions = "^3.2.3"
whitenoise = "^6.6.0"
```


## Development Installation (manual)

1. Clone the repository:
    ```sh
    git clone https://github.com/noatgnu/curtainbe.git
    cd curtainbe
    ```

2. Install dependencies using Poetry:
    ```sh
    poetry install
    ```
   
3. Activate the virtual environment:
    ```sh
    poetry shell
    ```
   
4. Apply database migrations:
    ```sh
    python manage.py migrate
    ```
   
5. Run the development server:
    ```sh
    python manage.py runserver
    ```
   
## Setup with Docker

1. **Clone the repository:**
    ```sh
    git clone https://github.com/noatgnu/curtainbe.git
    cd curtainbe
    ```
   
2. **Build the Docker image:**
    ```sh
    docker compose build
    ```

3. **Start the containers:**
    ```sh
    docker compose up
    ```
   
4. **Apply database migrations:**
    ```sh
    docker compose exec web python manage.py migrate
    ```
   
5. **Create a superuser:**
    ```sh
    docker compose exec -it web python manage.py createsuperuser
    ```
   
6. **Access the development server:**
    ```sh
    http://localhost:8000
    ```
   
## License
This project is licensed under the MIT License.
```