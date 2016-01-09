from fabric.tasks import execute
from fabric.operations import local as lrun, run
from fabric.api import run, sudo,put,prompt,cd,env,get,task
from fabric.contrib.files import append,exists, is_link
import os,sys
import string, random
import pycurl, json
import MySQLdb
import datetime
from boto.s3.connection import S3Connection
from boto.s3.connection import Location

env.use_ssh_config = True

USER = ''
AWS_KEY = ''
AWS_SECRET = ''

@task
def restore_database(domain,date):
	f_domain = domain.replace('.au','').replace('.com','').replace('.net','').replace('-','')
	f_domain = f_domain[:16] if len(f_domain) > 16 else f_domain
	
	conn = S3Connection(AWS_KEY,AWS_SECRET)
	bucket = conn.get_bucket('db.server.mysql.backups')
	
	bucket_list = bucket.list()
	key = '{0}-{1}.sql.gz'.format(f_domain, date)
	file = '/tmp/'+key
	for dump in bucket_list:
		#print str(dump.key)
		if str(dump.key) == key:
			dump.get_contents_to_filename(file)

	if env.host_string == 'db1':	
		put(file, '/tmp')
		
	run('gunzip {0}'.format(file))
	file = file.replace('.gz','')
	run("mysql --default-character-set=utf8 {0} < {1}".format(f_domain, file))
	
	local = 'local.'
	if env.host_string == 'db1':
		local = ''
		
	mysql("use {0}; update core_config_data set value='http://www.{2}{1}/' where path = 'web/unsecure/base_url';".format(f_domain, domain,local))
	mysql("use {0}; update core_config_data set value='https://www.{2}{1}/' where path = 'web/secure/base_url';".format(f_domain, domain,local))
	run('rm {0}'.format(file))
			
@task
def all_prod():
	env.hosts = ['web3','web4','lb1','db1']
	env.password = ''

@task
def prod():
	env.hosts = ['web3','web4']
	env.password = ''

@task
def prod_single():
	env.hosts = ['web3']	
	env.password = ''
	
@task
def prod_db():
	env.hosts = ['db1']
	env.password = ''
	
@task
def prod_lb():
	env.hosts = ['lb1']
	env.password = ''

@task
def localhost():
	env.run = lrun
	env.hosts = ['localhost']
	env.password = ''

@task
def service(service, action):
    sudo("service {0} {1}".format(service,action),warn_only=True)

@task
def update():
    sudo("apt-get update")

@task
def upgrade():
    sudo("apt-get upgrade")
	
def mysql(command):	
	run('mysql --default-character-set=utf8 -e "%s"' % (command))		
	
@task
def git_pull(domain,env='test'):

	directory = domain
			
	if exists('/tmp/{0}.mounted'.format(domain), use_sudo=True):
		
		sudo('umount -l /srv/www/{0}/media'.format(domain))		
		run('rm /tmp/{0}.mounted'.format(domain))
		
		with cd("/srv/www/{0}".format(domain)):
			run("git fetch --all",warn_only=True)
			run("git reset --hard origin/master",warn_only=True)
			
		sudo('chown -R www-data:www-data /srv/www/{0}'.format(domain))
		sudo('chmod -R g+rw /srv/www/{0}'.format(domain))	
			
		run('cp -R /srv/www/{0}/media /tmp/{0}'.format(directory))		
		cp_media = 	'/tmp/{0}'.format(directory)	
		
		#mount nfs share on lb1 and update fstab
		sudo('sudo mount -t nfs -o proto=tcp,port=2049 192.168.150.78:/export/{0}/media /srv/www/{0}/media'.format(directory))
		
		run('cp -R {0}/* /srv/www/{1}/media/. '.format(cp_media,directory))	
		run('rm -rf {0}'.format(cp_media))		
		run('touch /tmp/{0}.mounted'.format(domain))
	
	else:
		with cd("/srv/www/{0}".format(domain)):
			#run("git pull",warn_only=True)
			run("git fetch --all",warn_only=True)
			run("git reset --hard origin/master",warn_only=True)

	if is_link('/srv/www/{0}/app/etc/local.xml'.format(domain)):
		run('rm /srv/www/{0}/app/etc/local.xml'.format(domain))
	run('ln -s /srv/www/{1}/app/etc/local.xml.{0} /srv/www/{1}/app/etc/local.xml'.format(env,directory))
	
	
@task
def nfs_server(domain,directory=''):
	if directory=='':
		directory = domain
		
	if not exists('/export/{0}'.format(domain), use_sudo=True):
		sudo('mkdir /export/{0}'.format(directory))
		sudo('mkdir /export/{0}/media'.format(directory))
		sudo('echo "/export/{0}/media *(rw,nohide,insecure,no_subtree_check,async)" >> /etc/exports'.format(directory))
		sudo('chmod -R 777 /export/{0}'.format(directory))
		sudo('sudo service nfs-kernel-server restart')
	
@task
def chmod_nfs_server(domain,directory=''):
	if directory=='':
		directory = domain
	sudo('chmod -R 777 /export/{0}'.format(directory))
	
@task
def nfs_client(domain,directory=''):		
	if directory=='':
		directory = domain
			
	if not exists('/tmp/{0}.mounted'.format(domain), use_sudo=True):
		run('touch /tmp/{0}.mounted'.format(domain))		
		run('cp -R /srv/www/{0}/media /tmp/{0}'.format(directory))		
		cp_media = 	'/tmp/{0}'.format(directory)
		
		#mount nfs share on lb1 and update fstab
		sudo('sudo mount -t nfs -o proto=tcp,port=2049 192.168.150.78:/export/{0}/media /srv/www/{0}/media'.format(directory))
		sudo('echo "192.168.150.78:/export/{0}/media /srv/www/{0}/media   none    bind  0  0" >> /etc/fstab'.format(directory))
		
		run('cp -R {0}/* /srv/www/{1}/media/. '.format(cp_media,directory))	
		run('rm -rf {0}'.format(cp_media))	
	
@task
def git_clone(domain,directory='',env='dev'):
	if directory=='':
		directory = domain
		
	if not exists('/srv/www/{0}'.format(domain)):
		with cd("/srv/www/"):
			run("git clone git@bitbucket.org:<github>/{0}.git {1}".format(domain, directory),warn_only=True)

	if is_link('/srv/www/{0}/app/etc/local.xml'.format(domain)):
		run('rm /srv/www/{0}/app/etc/local.xml'.format(domain))
	run('ln -s /srv/www/{1}/app/etc/local.xml.{0} /srv/www/{1}/app/etc/local.xml'.format(env,directory))
	
	sudo('chown -R www-data:www-data /srv/www/{0}'.format(directory))
	sudo('chmod -R g+rw /srv/www/{0}'.format(directory))
	
	
@task
def cp_site(copy='',paste='',env='dev'):

	if not exists('/srv/www/{0}'.format(paste)):
		run('cp -R /srv/www/{0} /srv/www/{1}'.format(copy,paste))	
	
	if is_link('/srv/www/{0}/app/etc/local.xml'.format(paste)):
		run('rm /srv/www/{0}/app/etc/local.xml'.format(paste))
	run('ln -s /srv/www/{1}/app/etc/local.xml.{0} /srv/www/{1}/app/etc/local.xml'.format(env,paste))

	sudo('chown -R www-data:www-data /srv/www/{0}'.format(paste))
	sudo('chmod -R g+rw /srv/www/{0}'.format(paste))	

@task
def create_config_symlink(domain,directory='',env='dev'):	
	if directory=='':
		directory = domain
		
	if is_link('/srv/www/{0}/app/etc/local.xml'.format(directory)):
		run('rm /srv/www/{0}/app/etc/local.xml'.format(directory))
	run('ln -s /srv/www/{1}/app/etc/local.xml.{0} /srv/www/{1}/app/etc/local.xml'.format(env,directory))		
	
@task
def multi_site_create(file,env='dev'):
	urls = []

	with open(file, 'rU') as f:
		for line in f:
			urls.append(line)	
	
	for url in urls:
		domain = url.strip()
		print 'creating site for: {0}'.format(domain)
		
		print 'creating nginx config'	
		create_nginx_config('local.'+domain)

		print 'creating databases'
		create_databases(domain)
		
		print 'loading databases'
		load_databases(domain=domain,init='1')
		
		print 'cloning magento'
		clone_magento('local.'+domain)
	
# run using prod_single?
@task
def multi_site_deploy(file):
	urls = []

	with open(file, 'rU') as f:
		for line in f:
			urls.append(line)	
	
	for url in urls:
		domain = url.strip()
		f_domain = domain.replace('.au','').replace('.com','').replace('.net','')
		test_domain = f_domain+'.dashdevelopers.com.au'
		
		print 'creating site for: {0}'.format(domain)
		
		#run per web app server
		print 'creating nginx config'	
		execute(create_nginx_config, hosts=['web3','web4'], domain=test_domain)
		execute(create_nginx_config, hosts=['web3','web4'], domain=domain)
		
		#creates database, creates db users, auto generates db user password, adds details to website db, adds new wordpress user
		print 'creating databases'
		execute(create_databases, hosts=['db1'], domain=domain)
		
		#loads using magento skeleton if init=1, if init=0 then dumps out database with f_domain and loads it
		print 'loading databases'
		execute(load_databases, hosts=['db1'], domain=domain,init='0')
		
		#run per web app server
		print 'git cloning project'
		execute(git_clone, hosts=['web3','web4'], domain=domain,directory=domain,env='prod')
		execute(cp_site, hosts=['web3','web4'], copy=domain,paste=test_domain,env='test')
		#need to clear redis cache
		
		print 'creating nfs server share'
		execute(nfs_server, hosts=['lb1'], domain=domain, directory=domain)
		execute(nfs_server, hosts=['lb1'], domain=test_domain, directory=test_domain)	
		
		#run per web app server
		print 'creating nfs client share'
		execute(nfs_client, hosts=['web3','web4'], domain=domain, directory=domain)
		execute(nfs_client, hosts=['web3','web4'], domain=test_domain, directory=test_domain)
		
		#need to chown nsf server share after files are copied over
		execute(chmod_nfs_server, hosts=['lb1'], domain=domain, directory=domain)
		execute(chmod_nfs_server, hosts=['lb1'], domain=test_domain, directory=test_domain)
		
		
@task
def create_nginx_config(domain):
	#create nginx config	
	if not exists('/etc/nginx/sites-enabled/{0}'.format(domain)):
		sudo('cp /etc/nginx/sites-available/magento_default /etc/nginx/sites-available/{0}'.format(domain))
		sudo('sed -i -- "s/magento_default/{0}/g" /etc/nginx/sites-available/{0}'.format(domain))

		if exists('/etc/nginx/sites-enabled/{0}'.format(domain), use_sudo=True):
			sudo('rm /etc/nginx/sites-enabled/{0}'.format(domain))
		sudo('ln -s /etc/nginx/sites-available/{0} /etc/nginx/sites-enabled/{0}'.format(domain))
		sudo('service nginx restart')
	
#simple table used to keep track of websites database information
#has web interface 192.168.1.103:88/html/db_users.php
@task
def add_website(domain, password):
	f_domain = domain.replace('.au','').replace('.com','').replace('.net','').replace('-','')
	f_domain = f_domain[:16] if len(f_domain) > 16 else f_domain

	conn = MySQLdb.connect(host="127.0.0.1",port=3307,user="websites", passwd="websites", db="websites")
	cur = conn.cursor()
	sql = "insert into websites(domain, database_name, user, password, created_by, created) values ('{0}','{1}','{2}','{3}','{4}','{5}');".format(domain, f_domain, f_domain, password, USER, datetime.datetime.now().replace(microsecond=0))
	cur.execute(sql)
	conn.commit()
	conn.close()	
	
#adds user to wordpress website for account management, payments, etc
@task
def create_wordpress_user(domain, password):

	f_domain = domain.replace('.au','').replace('.com','').replace('.net','').replace('-','')
	f_domain = f_domain[:16] if len(f_domain) > 16 else f_domain
	now = datetime.datetime.now().replace(microsecond=0)
	
	conn = MySQLdb.connect(host="127.0.0.1",port=3307,user="", passwd="", db="")
	cur = conn.cursor()
	
	sql = "INSERT INTO wp_users (user_login, user_pass, user_nicename, user_email, user_url, user_registered,user_activation_key, user_status, display_name) VALUES ('{0}', MD5('{1}'), '{0}', 'admin@{2}', '{2}', '{3}', '', '0', '{0}');".format(f_domain, password, domain,now)
	cur.execute(sql)
	id = cur.lastrowid
	capabilities = 'a:1:{s:10:"subscriber";b:1;}'
	sql = "INSERT INTO wp_usermeta (umeta_id, user_id, meta_key, meta_value) VALUES (NULL, '{0}', 'wp_capabilities', '{1}'), (NULL, '{0}', 'wp_user_level', '0');".format(id,capabilities)
	cur.execute(sql)
	conn.commit()
	conn.close()
	
	
# NOTE: anything outside the run/sudo functions will run on localhost, so ssh tunnel to prod database needs to be enabled	
@task
def create_databases(domain):

	auto_generated = False

	# lookup auto generated password
	conn = MySQLdb.connect(host="127.0.0.1",port=3307,user="websites", passwd="websites", db="websites")
	cur = conn.cursor()
	sql = "select password from websites where domain = '{0}';".format(domain)
	try:
		print 'password found'
		cur.execute(sql)		
		result = cur.fetchone()
		password = result[0]
	except:
		password = ''
		
	if password=='' and env.host_string == 'localhost':
		print 'password not found.... auto generating password'
		auto_generated = True
		password = ''.join(random.SystemRandom().choice(string.ascii_letters + string.digits) for _ in range(16))
			
	#remove domain suffix and shorten to 16 characters if necesarry
	f_domain = domain.replace('.au','').replace('.com','').replace('.net','').replace('-','')
	f_domain = f_domain[:16] if len(f_domain) > 16 else f_domain
		
	mysql("CREATE USER '{0}'@'%' IDENTIFIED BY '{1}';".format(f_domain,password))
	mysql("CREATE DATABASE test_{0};".format(f_domain))
	mysql("GRANT ALL ON test_{0}.* TO '{0}'@'%' IDENTIFIED BY '{1}';".format(f_domain,password))
	mysql("CREATE DATABASE {0};".format(f_domain))
	mysql("GRANT ALL ON {0}.* TO '{0}'@'%' IDENTIFIED BY '{1}';".format(f_domain,password))
	
	if auto_generated:
		add_website(domain, password)
		create_wordpress_user(domain, password)
			
@task
def load_databases(domain,init):
	
	f_domain = domain.replace('.au','').replace('.com','').replace('.net','').replace('-','')
	f_domain = f_domain[:16] if len(f_domain) > 16 else f_domain
	
	if init=='1':
		#already exists on db server so no need to copy it over
		f_sql_file = '/home/web_user/magento_skeleton_db_init.sql'
		lrun('cp {0} /tmp/.'.format(f_sql_file))
		f_sql_file = '/tmp/magento_skeleton_db_init.sql'
	else:
		sql_file = f_domain+'.sql'
		lrun('mysqldump {0} > /tmp/{1}'.format(f_domain,sql_file))
		f_sql_file = '/tmp/'+sql_file
		
	#copy sql dump over to db server
	if env.host_string == 'db1':	
		put(f_sql_file, '/tmp')
		
	run("mysql --default-character-set=utf8 test_{0} < {1}".format(f_domain, f_sql_file))
	run("mysql --default-character-set=utf8 {0} < {1}".format(f_domain, f_sql_file))

	#remove uploaded dump sql file
	#run('rm {0}'.format(f_sql_file))
	#if init=='0':
	#	lrun('rm {0}'.format(f_sql_file))
		
	# if prod update url
	if env.host_string == 'db1':
		update_url(domain)

@task
def update_url(domain):
	f_domain = domain.replace('.au','').replace('.com','').replace('.net','')
	f_domain = f_domain[:16] if len(f_domain) > 16 else f_domain
	test_domain = domain.replace('.com','').replace('.au','').replace('.net','').replace('-','')
	mysql("use test_{0}; update core_config_data set value='http://www.{1}.demowebsite.com.au/' where path = 'web/unsecure/base_url';".format(f_domain, test_domain))
	mysql("use test_{0}; update core_config_data set value='https://www.{1}.demowebsite.com.au' where path = 'web/secure/base_url';".format(f_domain, test_domain))
	mysql("use {0}; update core_config_data set value='http://www.{1}/' where path = 'web/unsecure/base_url';".format(f_domain, domain))
	mysql("use {0}; update core_config_data set value='https://www.{1}/' where path = 'web/secure/base_url';".format(f_domain, domain))	

	
@task
def create_repo(domain):

	url = "https://api.bitbucket.org/2.0/repositories/<bitbucket>/{0}".format(domain)
	user_pwd = "<bitbucket>:<bitbucket_pw>"
	data = json.dumps({"scm": "git", "is_private": "true", "fork_policy": "no_public_forks", "language": "php", "has_issues": "true" })
	
	c = pycurl.Curl()
	c.setopt(pycurl.URL, url)
	c.setopt(pycurl.USERPWD, user_pwd)
	c.setopt(pycurl.HTTPHEADER, ['Content-Type: application/json'])
	c.setopt(pycurl.POST, 1)
	c.setopt(pycurl.POSTFIELDS, '{0}'.format(data))
	c.perform()
	
@task
def delete_repo(domain):

	url = "https://api.bitbucket.org/2.0/repositories/<bitbucket>/{0}".format(domain)
	user_pwd = "<bitbucket>:<bitbucket_pw>"
	
	c = pycurl.Curl()
	c.setopt(pycurl.URL, url)
	c.setopt(pycurl.USERPWD, user_pwd)
	c.setopt(pycurl.HTTPHEADER, ['Content-Type: application/json'])
	c.setopt(pycurl.CUSTOMREQUEST, "DELETE")
	c.perform()	
	
#copies magento skeleton and created bitbucket repo	
@task
def clone_magento(domain):
	#copy base magento skeleton and initialize git
	run('cp -R /srv/www/magento_skeleton /srv/www/{0}'.format(domain))
	
	f_domain = domain.replace('local.','')
	create_repo(f_domain)
	#create_config_symlink(domain, env='dev')
	
	with cd('/srv/www/{0}'.format(domain)):
		run('rm -rf .git')
		run('git init')
		run('git remote add origin git@bitbucket.org:<bitbucket>/{0}.git'.format(f_domain))
		#run('git push -u origin --all')
		#run('git push -u origin --tags')
	
	#update perms
	sudo('chown -R www-data:www-data /srv/www/{0}'.format(domain))
	sudo('chmod -R g+rw /srv/www/{0}'.format(domain))
	
	
		