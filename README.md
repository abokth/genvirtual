# genvirtual

Genvirtual is Python utility producting Postfix configuration (database) files from the contents of an SQL database.

## Installation

TODO

## Usage

Copy sample.ini and fetch_sample_data.py to new files, typically named after your organisation. Edit them to suit your database content.

Run:

```bash
set -e
./bin/genvirtual myorg.ini
postmap virtual
sudo cp virtual /etc/postfix/virtual.new
sudo cp virtual.db /etc/postfix/virtual.db.new
sudo mv /etc/postfix/virtual{.new,}
sudo mv /etc/postfix/virtual.db{.new,}
```

Note the [Postfix database readme](http://www.postfix.org/DATABASE_README.html#safe_db) on safely updating the database files.

## Contributing
Pull requests are welcome. For major changes, please open an issue first to discuss what you would like to change.

## License
[MIT](https://choosealicense.com/licenses/mit/)

