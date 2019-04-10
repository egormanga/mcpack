#!/usr/bin/python3
# McPack

from utils import *; logstart('McPack')

mc_version = None
db.setfile('./.mcpack')
db.setbackup(False)
db.setnolog(True)
db.register('mc_version')

class CurseForge:
	cfbaseurl = "https://minecraft.curseforge.com"

	def url(spec): return lambda f: lambda self, *args, **kwargs: f(self, bs4.BeautifulSoup(requests.get(f"{self.cfbaseurl}/{spec.format(*args)}").text, 'html.parser'), **kwargs)

	@staticmethod
	def _get_listing(l):
		return [{'name': re.search(r'.*/(.+?)/?$', i.find(class_='name-wrapper').a['href'])[1], 'title': i.find(class_='name-wrapper').text.strip(), 'desc': i.find(class_='description').text.strip()} for i in l.findAll(class_='details') if not i.find(class_='no-results')]

	@url("/mc-mods?page={0}")
	def mcmods(self, p):
		return self._get_listing(p.findAll(class_='listing')[1])

	@url("/projects/{0}")
	def project(self, p):
		return {'name': p.find(class_='project-title').text.strip(), 'desc': p.find(class_='project-description').text.strip()}

	@url("/projects/{0}/relations/dependencies?filter-related-dependencies=3")
	def dependencies(self, p):
		return self._get_listing(p.find(class_='listing'))

	@url("/projects/{0}/files")
	def project_versions(self, p):
		return {i.text.strip(): i['value'] for i in p.find(id='filter-game-version').findAll('option')}

	@url("/projects/{0}/files?filter-game-version={1}")
	def project_newest_file_id(self, p, version='', min_type='A'): # TODO: support pagination, optimize type checking
		return next(filter(lambda x: x.div['title'] in (('Alpha', 'Beta', 'Release') if (min_type == 'A') else ('Beta', 'Release') if (min_type in 'AB') else ('Release',)), p.findAll(class_='project-file-list-item'))).find(class_='project-file-name-container').a['href'].split('/')[-1]

	@url("/projects/{0}/files/{1}")
	def project_file_id_md5(self, p):
		return p.find(class_='md5').text.strip()

	def resolve_deps(self, name, r=None): # TODO: conflicts, optionals?; optimize (listing)?
		if (r is None): r = set()
		for i in S(self.dependencies(name))@['name']:
			r.add(i)
			self.resolve_deps(i, r)
		return r

def install(cargs): # TODO: more error messages
	db.load()
	if (not mc_version): exit("Set Minecraft version with `mcpack version` first.")
	cf = CurseForge()
	ok = True
	print("Checking mod name...", end=' ')
	try: print(cf.project(cargs.name)['name'])
	except Exception: sys.stdout.flush(); exit("mod not found")
	print("Resolving dependencies...")
	to_install = {cargs.name} | cf.resolve_deps(cargs.name)
	print("Mods to install:", S(' ').join(sorted(to_install)).wrap(72, loff=17))
	print("Checking versions...")
	file_ids = dict()
	ok = True
	for i in to_install:
		versions = cf.project_versions(i)
		if (mc_version not in versions): print(f"Mod {i} does not support Minecraft {mc_version}."); ok = False; continue
		try: file_ids[i] = cf.project_newest_file_id(i, versions[mc_version], min_type=('A' if (cargs.alpha) else 'B' if (cargs.beta) else 'R'))
		except Exception: print(f"Mod {i} doesn't have any{'' if (cargs.alpha) else ' release/beta' if (cargs.beta) else ' release'} versions on the first page."); ok = False
	if (not ok): exit("Aborting.")
	print("Downloading mods...")
	md5s = {i: cf.project_file_id_md5(i, file_ids[i]) for i in file_ids}
	installed = set()
	for i in os.listdir():
		m = re.match(r'(.*)-([\d\.]+)_(\d+)\.\w+', i)
		if (m is None): continue
		if (m[2] != mc_version):
			if (input(f"{m[1]} for {m[2]} is probably not compatible with Minecraft {mc_version}. Disable? [Y/n] ").strip().casefold() in 'y'):
				if (not os.path.isdir('Disabled')): os.mkdir('Disabled')
				shutil.move(i, 'Disabled/'+i)
				print(f"Disabled {m[1]}.")
			continue
		if (m[1] not in to_install): continue
		if (m[3] != file_ids.get(m[1])):
			print(f"Uninstalling {m[1]} version {m[3]} (old)")
			os.remove(i)
			continue
		if (hashlib.md5(open(i, 'rb').read()).hexdigest() == md5s[m[1]]): installed.add(m[1])
	for i in to_install:
		print(f"Installing {i}", end=' ')
		if (i in installed): print("...already installed"); continue
		else: print()
		r = requests.get(f"{cf.cfbaseurl}/projects/{i}/files/{file_ids[i]}/download", stream=True)
		fn = f"{i}-{mc_version}_{file_ids[i]}.{r.url.split('.')[-1]}"
		f = open(fn, 'wb')
		for c in progiter(r.iter_content(chunk_size=4096), math.ceil(int(r.headers.get('Content-Length'))/4096)): f.write(c)
		f.close()
		md5 = hashlib.md5(open(fn, 'rb').read()).hexdigest()
		if (md5 != md5s[i]):
			print(f"Error downloading {i}: md5 does not match ({md5} vs orig {md5s[i]}). Restart installation before playing.")
			ok = False
	if (ok): print("Installation successful.")

def version(cargs):
	global mc_version
	db.load()
	if (cargs.version is None): print(f"Current Minecraft version is {mc_version}."); return
	mc_version = cargs.version
	db.save()
	print(f"Successfully set Minecraft {mc_version} version.")

def main(f, cargs):
	try: return f(cargs)
	except Exception as ex: exception(ex)
	except KeyboardInterrupt as ex: exit(ex)

if (__name__ == '__main__'):
	subparser = argparser.add_subparsers(metavar='<action>')

	args_install = subparser.add_parser('install', help="Download a mod with all its dependencies.")
	args_install.add_argument('name')
	args_install.add_argument('--beta', action='store_true', help="Allow beta versions")
	args_install.add_argument('--alpha', action='store_true', help="Allow alpha and beta versions")
	args_install.set_defaults(func=install)

	args_version = subparser.add_parser('version', help="Get/set Minecraft version for this directory.")
	args_version.add_argument('version', nargs='?')
	args_version.set_defaults(func=version)

	argparser.set_defaults(func=lambda *args: sys.exit(argparser.print_help()))
	cargs = argparser.parse_args()
	logstarted(); exit(main(cargs.func, cargs))
else: logimported()

# by Sdore, 2019
