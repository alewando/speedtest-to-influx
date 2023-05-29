Tracking internet speed using influx and grafana

1. Install Ookla speedtest cli: [https://www.speedtest.net/apps/cli]
2. Clone git repo to /usr/local/src
   ```
   cd /usr/local/src
   git clone https://github.com/alewando/speedtest-to-influx.git
   ```
3. Link script to /usr/local/bin
	1. `ln -s /usr/local/src/speedtest-to-influx/speedtest-to-influx.py /usr/local/bin/speedtest-to-influx.py `
4. Create cron job
	1. `v /etc/cron.d/speedtest-to-influx`
```
	   SHELL=/bin/sh
	   PATH=/usr/local/sbin:/usr/local/bin:/sbin:/bin:/usr/sbin:/usr/bin
	   
	   05 3    * * *   root    /usr/local/bin/speedtest-to-influx.py
``` 
5. Sample Influx query for dashboard:
   `SELECT mean("download.bandwidth") AS "Down", mean("upload.bandwidth") AS "Up" FROM "speedtest" WHERE $timeFilter GROUP BY time($__interval), "isp" fill(linear)`
