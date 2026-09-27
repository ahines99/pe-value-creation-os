-- Local development only. Real environments set role passwords from the secret manager (PVC-093).
alter role pvc_app with password 'pvc_app_dev';
alter role pvc_readonly with password 'pvc_readonly_dev';
