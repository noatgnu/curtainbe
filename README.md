# Curtain Backend

This project is the backend for Curtain. It includes models for managing curtains, user public keys, social platforms, data filter lists, kinase library models, curtain access tokens, AES encryption factors, data hashes, and last access timestamps.

## Setup

You can set up and run this project using Docker Compose directly or the provided Ansible playbook.

### Using Docker Compose

1. **Clone the repository**:
    ```sh
    git clone https://github.com/noatgnu/curtainbe.git
    cd curtainbe
    ```

2. **Create environment variables file**:
    Create a `.env` file in the project root and add the necessary environment variables.

3. **Build and start Docker containers**:
    ```sh
    docker-compose up -d
    ```

4. **Apply migrations**:
    ```sh
    docker-compose exec web python manage.py migrate
    ```

5. **Create a superuser**:
    ```sh
    docker-compose exec web python manage.py createsuperuser
    ```

6. **Access the application**:
    Open your browser and go to `http://localhost:8000`.

### Using Ansible Playbook

1. **Clone the repository**:
    ```sh
    git clone https://github.com/noatgnu/curtainbe.git
    cd curtainbe
    ```

2. **Create environment variables file**:
    Create a `.env` file in the project root and add the necessary environment variables.

3. **Run the Ansible playbook**:
    ```sh
    ansible-playbook -i inventory ansible.playbook.yml -e "domain_name=yourdomain.com email=youremail@example.com"
    ```
4. **Access the application**:
    Open your browser and go to `https://yourdomain.com`.


## Contributing

1. **Fork the repository**.
2. **Create a new branch**:
    ```sh
    git checkout -b feature/your-feature-name
    ```
3. **Commit your changes**:
    ```sh
    git commit -m 'Add some feature'
    ```
4. **Push to the branch**:
    ```sh
    git push origin feature/your-feature-name
    ```
5. **Open a pull request**.

## License

This project is licensed under the MIT License.