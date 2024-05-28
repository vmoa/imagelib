# Cheatsheet to rebuild database from scratch

These instructions will destory and rebuild the databases from scratch.  This should only be something that
a developer does to test a new feature. It will likely never to be done in production, though in *theory*
it should be okay, just time consuming.

**CAUTION: Only do this if you (think you) know what you're doing!**

```
mv fits.db fits.db-OLD
rm fits.last_run
python3 ./fitsdb.py create
python3 ./catalog.py create ~/Downloads/SAC_DeepSky_ver81/SAC_DeepSky_Ver81_QCQ.TXT
python3 ./fitsfiles.py
```
