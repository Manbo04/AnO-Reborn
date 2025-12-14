# The script to run if Celery or RabbitMQ fails.
import os


def main():
    current_dir = os.getcwd()
    new_dir = current_dir.replace("\\scripts", "")
    os.chdir(new_dir)
    # Import tasks after chdir to ensure module imports resolve correctly
    import tasks  # imported for side-effects (no direct reference)  # noqa: F401


if __name__ == "__main__":
    main()
