# Affairs-and-Order

Affairs & order is a nation simulation game, where you can make your own nation, build a military and industry, and declare war.

## Repo installation.

1. Install Git and add Git to PATH. https://stackoverflow.com/questions/26620312/installing-git-in-path-with-github-client-for-windows
2. Type `git clone https://github.com/delivey/AnO.git` in the folder you want the repo to be cloned in.

## Flask / Requirements

1. Install Python (Recommended: 3.10.x). This project is tested on **Python 3.8, 3.10 and 3.14** (CI matrix). For production deployments on Railway we recommend using `python-3.10.19` in `runtime.txt` or setting the service runtime to Python 3.10.x.
2. Create and activate a virtual environment (recommended):
   - `python3 -m venv .venv`
   - `source .venv/bin/activate`
3. Run `pip install -r requirements.txt` to install the project's dependencies.
4. Start the app for development:
   - `flask run`
5. Visit `http://127.0.0.1:5000/` in your browser to use the site.

## PostgresQL

### Windows
1. Get the `.exe` installer from here: `https://www.enterprisedb.com/downloads/postgres-postgresql-downloads`. Download version 10.14
2. Run the installer, remember your set settings.
3. Set them in the .env file (if you haven't already rename .env.example to .env)
4. Run the `create_db.py` file in AnO/affo to create your database instance.
### Debian
1. Follow [this guide](https://www.digitalocean.com/community/tutorials/how-to-install-and-use-postgresql-on-ubuntu-18-04) to setup Postgres
2. Set Postgres variables in the .env file (if you haven't already rename .env.example to .env)
3. Run the `create_db.py` file in AnO/affo to create your database instance.

# No need for the ones below FOR DEVELOPMENT

## RabbitMQ

### Arch

1. Install rabbitmq by typing `pacman -S rabbitmq`
2. Follow this guide: https://docs.celeryproject.org/en/stable/getting-started/brokers/rabbitmq.html and name your username, password and vhost `ano`
3. Run rabbitmq by typing: `sudo rabbitmq-server`

### Debian

1. Follow this guide to install RabbitMQ: https://www.vultr.com/docs/how-to-install-rabbitmq-on-ubuntu-16-04-47 and name your username, password and vhost `ano`
2. Stop the rabbitmqctl service for naming usernames, vhosts, etc by typing: `sudo rabbitmqctl stop`
3. Run the RabbitMQ broker by typing: `sudo rabbitmq-server`

## Celery

#### IMPORTANT NOTE: open all your terminals using `sudo -i`, this will give root access to celery.
1. Navigate into the `AnO` folder.
2. Run the beat pool by running: `celery -A app.celery beat --loglevel=INFO` in the terminal.
3. Run *1* worker by running: `celery -A app.celery worker --loglevel=INFO` in another terminal window.
4. For `celery` to work, RabbitMQ must be running.
