set +x;
set -e;

# create dump if not dump.sql exists
if [ ! -f dump.sql ]; then
    # get envvars from .env file
    export $(grep -v '^#' .env.preprod.local | xargs)
    POD=pg-rozert-pay-0
    kubectl -n rozert-pay-db exec -it $POD -- bash -c "PGPASSWORD=$POSTGRES_PASSWORD pg_dump --no-owner --exclude-table=part_config --exclude-table=part_config_sub -U $POSTGRES_USER $POSTGRES_DATABASE > dump.sql"

    # copy dump to local
    kubectl -n rozert-pay-db cp $POD:dump.sql dump.sql

    # remove exported envvars
    unset $(grep -v '^#' .env.preprod.local | sed -E 's/(.*)=.*/\1/' | xargs)
else
    echo "dump.sql already exists!"
fi

# export envvars from .env
export $(grep -v '^#' .env | xargs)

# drop db first?
read -p "Do you want to drop the database first? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]
then
    docker-compose down;
    rm -R ./volume_data/postgres/*;
    docker-compose up -d db;
    sleep 5
fi

# load dump via docker-compose
docker-compose exec -T db psql -U $POSTGRES_USER $POSTGRES_DATABASE < dump.sql

# up
make dev-up
