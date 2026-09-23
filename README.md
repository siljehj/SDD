# SDD

# SQL-BRUKER
### ENS
### 6769

# Database Setup

## Initial Setup

Start Docker Desktop and create the MySQL container:

~~~powershell
docker run --name fake-taxi-db -e MYSQL_ROOT_PASSWORD=6769 -p 3306:3306 -v fake-taxi-data:/var/lib/mysql -d mysql:8.0.39
~~~

Create the database and user:

~~~powershell
docker exec -it fake-taxi-db mysql -u root -p
~~~

~~~sql
CREATE DATABASE fake_taxi;
CREATE USER 'ENS'@'%' IDENTIFIED BY '6769';
GRANT ALL PRIVILEGES ON fake_taxi.* TO 'ENS'@'%';
FLUSH PRIVILEGES;
~~~

## Making Database Changes

### 1. Make the change in the database

Open the MySQL database:

~~~powershell
docker exec -it fake-taxi-db mysql -u root -p
~~~

Select the database:

~~~sql
USE fake_taxi;
~~~

Make your changes using SQL. For example, to add a person:

~~~sql
INSERT INTO Example (name)
VALUES ('Nora');
~~~

Check that the change worked:

~~~sql
SELECT * FROM Example;
~~~

### 2. Update the shared SQL file

Exit MySQL:

~~~sql
exit;
~~~

Create an updated database dump:

~~~powershell
docker exec fake-taxi-db mysqldump -u root -p6769 fake_taxi > database\fake_taxi.sql
~~~

### 3. Commit and push the changes

~~~powershell
git add database/fake_taxi.sql
git commit -m "Update database"
git push
~~~

The updated `fake_taxi.sql` is now available to everyone through Git.