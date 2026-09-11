import getpass

from sqlmodel import SQLModel, Session, select

from main import User, engine, get_password_hash

def main():
    # Make sure the local database/tables exist.
    SQLModel.metadata.create_all(engine)

    username = input("Enter username: ").strip()

    if not username:
        print("Username cannot be empty.")
        return

    with Session(engine) as session:
        existing_user = session.exec(
            select(User).where(User.username == username)
        ).first()

        if existing_user:
            print(f"User '{username}' already exists locally.")
            return

        password = getpass.getpass("Enter password: ")
        confirm_password = getpass.getpass("Confirm password: ")

        if password != confirm_password:
            print("Passwords do not match.")
            return

        if not password:
            print("Password cannot be empty.")
            return

        user = User(
            username=username,
            hashed_password=get_password_hash(password),
        )

        session.add(user)
        session.commit()

        print(f"Local user '{username}' created successfully!")

if __name__ == "__main__":
    main()
