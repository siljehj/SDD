# Database Setup

The database runs locally using MySQL in Docker. Each group member has their own local database, and `files/fake_taxi.sql` is used to share database changes through Git.

## Initial Setup

### 1. Start Docker

Open the terminal in VS Code and make sure it is set to Command Prompt.

Create the MySQL container:

    docker run --name fake-taxi-db -e MYSQL_ROOT_PASSWORD=6769 -p 3306:3306 -v fake-taxi-data:/var/lib/mysql -d mysql:8.0.39

Check that it is running:

    docker ps

### 2. Open MySQL

    docker exec -it fake-taxi-db mysql -u root -p6769

Create the database:

    CREATE DATABASE fake_taxi;

Create the database user:

    CREATE USER 'ENS'@'%' IDENTIFIED BY '6769';
    GRANT ALL PRIVILEGES ON fake_taxi.* TO 'ENS'@'%';
    FLUSH PRIVILEGES;

Select the database:

    USE fake_taxi;

Exit MySQL:

    exit;

### 3. Import the Existing Database

If `files/fake_taxi.sql` already contains the database structure/data, import it:

    docker exec -i fake-taxi-db mysql -u root -p6769 fake_taxi | files/fake_taxi.sql

The database is now set up.

## Getting New Database Changes

When someone else has made changes and pushed them to Git:

### 1. Get the latest SQL file

    git pull

### 2. Import the updated database

    docker exec -i fake-taxi-db mysql -u root -p6769 fake_taxi | files/fake_taxi.sql

### 3. Open the database

    docker exec -it fake-taxi-db mysql -u root -p6769

Select the database:

    USE fake_taxi;

### 4. See the tables

    SHOW TABLES;

### 5. See the content of a table

For example:

    SELECT * FROM Example;

To see the structure of a table:

    DESCRIBE Example;

### 6. Exit MySQL

    exit;

## Making New Database Changes

### 1. Open the database

    docker exec -it fake-taxi-db mysql -u root -p6769

Select the database:

    USE fake_taxi;

### 2. Make your changes

For example, to add a person:

    INSERT INTO Example (name)
    VALUES ('Nora');

Check that it worked:

    SELECT * FROM Example;

When finished, exit MySQL:

    exit;

### 3. Export the updated database

From the VS Code terminal:

    docker exec fake-taxi-db mysqldump -u root -p6769 fake_taxi | files/fake_taxi.sql

Make sure `fake_taxi.sql` is saved as UTF-8.

### 4. Push the changes to Git

    git add files/fake_taxi.sql
    git commit -m "Update database"
    git push

The other group members can now follow the Getting New Database Changes section.

## Database Workflow

    Make changes in MySQL
            ↓
    Exit MySQL
            ↓
    Export fake_taxi.sql
            ↓
    git add + commit + push
            ↓
    Other members: git pull
            ↓
    Import fake_taxi.sql
            ↓
    Open MySQL and check tables/data

Each person has their own local database. Git is used to share the `fake_taxi.sql` file between the group members.