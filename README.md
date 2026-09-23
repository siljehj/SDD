# Fake taxi

## Database Setup

Each group member runs their own local MySQL database using Docker.

### 1. Start Docker Desktop

Make sure Docker Desktop is running.

Check:

```powershell
docker --version
```

### 2. Create the MySQL Container

```powershell
docker run --name fake-taxi-db -e MYSQL_ROOT_PASSWORD=6769 -p 3306:3306 -d mysql:8.0.39
```

### 3. Create the Database

```powershell
docker exec -it fake-taxi-db mysql -u root -p6769
```

Then in MySQL:

```sql
CREATE DATABASE fake_taxi;
```

## Getting Database Changes

When someone has pushed changes to the database:

```powershell
git pull
```

Then import the updated database:

```powershell
Get-Content database/fake_taxi.sql | docker exec -i fake-taxi-db mysql -u root -p6769 fake_taxi
```

Your local database is now updated.

## Making Database Changes

Make your changes in your local `fake_taxi` database.

When you are finished, create a new SQL dump:

```powershell
docker exec fake-taxi-db mysqldump -u root -p6769 fake_taxi > database\fake_taxi.sql
```

Then commit and push the changes:

```powershell
git add database/fake_taxi.sql
git commit -m "Update database"
git push
```

Other group members can then use the **Getting Database Changes** instructions to update their local database.

## Running the Python Code

Install the required packages:

```powershell
pip install -r Files/requirements.txt
```

Then run the example:

```powershell
python Files/example.py
```