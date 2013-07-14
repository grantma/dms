# Cron jobs for the DMS system

# m h  dom mon dow   command
# Clean up DMS database
#12 0 * * * root /usr/bin/zone_tool vacuum_all
# Backup the database 
30 0 * * * root /usr/sbin/dms_dumpdb

# For use with DR, replicate etckeeper archive every 4 hours
#7 */4 * * * root  cd /etc && /usr/bin/git fetch --quiet shalom-dr

