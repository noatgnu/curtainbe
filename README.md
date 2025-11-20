# Curtain Backend

This is the backend for the Curtain application, a Django-based platform for sharing and managing scientific data.

## Overview

The Curtain backend provides a RESTful API for managing "Curtains", which are shared datasets or files. The platform includes features for user authentication, data encryption, and integration with the DataCite service for creating Digital Object Identifiers (DOIs) for datasets.

## Main Features

*   **Curtain Management**: Create, update, and delete Curtains. Each Curtain can have multiple owners and can be set to expire after a certain period.
*   **File Sharing**: Upload and download files associated with Curtains. The system supports both cloud and local file storage.
*   **DataCite Integration**: A complete workflow for registering datasets with DataCite and obtaining a DOI, turning them into citable academic works.
*   **User Management**: User authentication via email/password or ORCID. Users can manage their own API keys and public keys.
*   **Encryption**: Support for end-to-end encryption of Curtain data.
*   **API Access**: The application is primarily API-driven, with support for API key authentication for programmatic access.
*   **Background Jobs**: Long-running tasks, such as comparing data from multiple Curtains, are handled by background workers using Django-RQ.

## API Endpoints

The API is built using Django Rest Framework. The main endpoints are:

*   `/api/curtain/`: Manages Curtains.
*   `/api/datacite/`: Manages the DataCite DOI registration process.
*   `/api/users/`: Manages users.
*   `/api/keys/`: Manages user API keys.
*   `/api/public_keys/`: Manages user public keys.
*   `/api/data_filter_lists/`: Manages user-defined data filters.

## Getting Started

### Prerequisites

*   Python 3.x
*   Poetry
*   Django

### Installation

1.  Clone the repository.
2.  Install the dependencies using Poetry:
    ```bash
    poetry install
    ```
3.  Set up the database:
    ```bash
    python manage.py migrate
    ```
4.  Run the development server:
    ```bash
    python manage.py runserver
    ```

### Running with Docker

The project also includes a `docker-compose.public.yml` file for running the application in a containerized environment.

```bash
docker-compose -f docker-compose.public.yml up
```
