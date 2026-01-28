#!/usr/bin/env python3
# MCPack

import yaml, requests
from concurrent.futures import ThreadPoolExecutor
from packaging import version
from utils.nolog import *
from .config import API_KEY

def print_state(c, t): print(f"\033[1;9{c}m==>\033[m \033[1m{t}\033[22m")
def print_info(c, t): print(f"   \033[1;9{c}m>\033[m {t}")

class CurseForgeAPI:
	class Game:
		MINECRAFT = 432

	class Class:
		MOD = 6
		SHADER = 6552

	api_base_url = "https://api.curseforge.com/v1"
	api_headers = {'User-Agent': None, 'X-API-Key': API_KEY}

	@classmethod
	@cachedfunction
	def api_get(cls, path, **kwargs):
		r = requests.get(f"{cls.api_base_url}/{path.lstrip('/')}", headers=cls.api_headers, params=kwargs)
		if (not r.ok): r.raise_for_status()
		return S(r.json()['data'])

	@classmethod
	def api_paginate(cls, *args, _paginate=True, **kwargs):
		if (not _paginate): return cls.api_get(*args, **kwargs)

		ii = int()
		while (True):
			r = cls.api_get(*args, **kwargs, index=ii)
			if (not r): break
			yield from r
			ii += len(r)

	def search(self, name, *, gameId=Game.MINECRAFT, classId=Class.MOD, sortField=2, sortOrder='desc', **kwargs):
		return self.api_paginate('/mods/search',
			gameId=gameId,
			classId=classId,
			searchFilter=name,
			sortField=sortField,
			sortOrder=sortOrder,
			**kwargs
		)

	def getAddon(self, addonId):
		return self.api_get(f"/mods/{addonId}")

	def getAddonBySlug(self, slug):
		return only(i for i in self.search(slug, _paginate=False) if i['slug'] == slug)

	def getAddonFiles(self, addonId, gameVersion=None, **kwargs):
		if (gameVersion is not None): parseargs(kwargs, gameVersion=gameVersion)
		return self.api_paginate(f"/mods/{addonId}/files", **kwargs)

	def getAddonFileInfo(self, addonId, fileId):
		return self.api_get(f"/mods/{addonId}/files/{fileId}")

	def getAddonFileDownloadUrl(self, addonId, fileId):
		return self.api_get(f"/mods/{addonId}/files/{fileId}/download-url")

class MCPack(Slots):
	mc_version: str | None
	loaders: tuple[str] | None
	mod_list: list[int]
	skip_version: list[str]
	default_filename = 'mcpack.json'

	@classmethod
	def open(cls, file=None):
		if (file is None): file = cls.default_filename
		r = cls()
		if (isinstance(file, str)):
			if (not os.path.isfile(file)): return r
			file = open(file, 'r')
		for k, v in json.load(file).items():
			setattr(r, k, v)
		return r

	def save(self, file=None):
		if (file is None): file = self.default_filename
		if (isinstance(file, str)): file = open(file, 'w')
		file.write(json.dumps({i: getattr(self, i) for i in self.__slots__}, indent=2) + '\n')

	@staticmethod
	def file_versions(file: dict):
		return {k: frozenset(map(operator.itemgetter(1), v)) for k, v in groupby(((i['gameVersionTypeId'], (i['gameVersion'] or i['gameVersionName'])) for i in file.get('sortableGameVersions', ())), key=operator.itemgetter(0))}

	def version_filename(self, file):
		vers = {j for i in self.file_versions(file).values() for j in i if j[0].isdigit()}
		loaders = sorted(j for i in self.file_versions(file).values() for j in i if not j[0].isdigit())
		return f"{self.mc_version if (self.mc_version in vers) else max(vers, key=version.parse)}-{'_'.join(loaders)}_{file['id']}.{file['fileName'].rpartition('.')[2]}"

@apcmd(metavar='<action>')
@aparg('-t', '--type', choices=tuple(i.lower() for i in dir(CurseForgeAPI.Class) if not i.startswith('_')), default='mod')
@aparg('name', metavar='<name>', nargs='A...')
def add(cargs):
	""" Add a mod to the bundle. """

	mcpack = MCPack.open()

	cf = CurseForgeAPI()

	name = ' '.join(cargs.name).strip()
	res = cf.search(name, classId=getattr(CurseForgeAPI.Class, cargs.type.upper()))
	l = sorted(res, key=lambda x: (not x['slug'].startswith(name), x['isFeatured'], -x['downloadCount'], x['name']))
	width = os.get_terminal_size()[0]
	for ii, mod in enumerate(l, 1):
		vers = set(map(operator.itemgetter('gameVersion'), mod['latestFilesIndexes']))
		s = f"\033[7;33m{ii}\033[m \033[1m{mod['name'].strip()}\033[22m (\033[96m{terminal_link(mod['links']['websiteUrl'], mod['slug'])}\033[39m) \033[2mby {mod['authors'][0]['name']}\033[22m \033[1;{92 if (mcpack.mc_version in vers) else 91 if (vers) else 2}m{f'{min(vers, key=version.parse)}–{max(vers, key=version.parse)}' if (vers) else '?'}\033[m \033[1;7;93m({mod['downloadCount']})\033[m "
		s2 = S(f"\033[1;34m({S(', ').join(S(mod['categories'])@['name'])})\033[m" + ' \033[1;33;7m[added]\033[m'*(mod['id'] in mcpack.mod_list))
		loff = len(noesc.sub('', s))
		print(s + (s2.wrap(width-1, loff=loff+1) if (loff < width-10) else '\n'+s2.rjust(width)))
		print(' '*(len(Sint(ii))+3) + S(mod['summary']).wrap(width, loff=len(Sint(ii))+4))
		print()

	s = "Select mods to add (e.g. 1 2 3-5)"
	print_state(3, s)
	print_state(3, '-'*len(s))
	q = input('\1\033[1;93m\2==>\1\033[m\2 ')
	sel = [j for i in re.findall(r'(\d+)(?:-(\d+))?', q) for j in (range(int(i[0]), int(i[1])+1) if (i[1]) else (int(i[0]),))]
	mods = [l[i-1]['id'] for i in sel]

	nadded = len(set(mods) - set(mcpack.mod_list))
	mcpack.mod_list += mods
	mcpack.mod_list = S(mcpack.mod_list).uniquize()
	mcpack.save()

	print_state(2, f"Added {decline(nadded, ('new mod', 'new mods'))}.")

@apcmd(metavar='<action>')
@aparg('name')
def remove(cargs):
	""" Remove mod from bundle. """

	mcpack = MCPack.open()

	cf = CurseForgeAPI()

	l = mcpack.mod_list
	w = os.get_terminal_size()[0]
	for ii, i in enumerate(l):
		a = cf.getAddon(i)
		if (cargs.name.strip() == a['slug'] or cargs.name.strip().casefold() == a['name'].strip().casefold()): break
	else: print_state(1, "No such mod."); return

	for f in cf.getAddonFiles(a['id'], gameVersion=mcpack.mc_version):
		#fn = f"{a['name'].strip()}-{version_filename(f['latestFiles'][0])}"
		fn = f['fileName']
		if (os.path.exists(fn)):
			if (not os.path.isdir(dirname := 'Removed')): os.mkdir(dirname)
			shutil.move(fn, os.path.join(dirname, fn))

	del mcpack.mod_list[ii]
	mcpack.save()

	print_state(2, f"Removed '{a['name'].strip()}'.")

@apcmd(metavar='<action>')
def list(cargs):
	""" List mods in bundle. """

	mcpack = MCPack.open()

	cf = CurseForgeAPI()

	with ThreadedProgressPool(1, fixed=True, add_speed_eta=True) as pp:
		pp.p[0].mv = len(mcpack.mod_list)

		def load(id_):
			try: return cf.getAddon(id_)
			finally: pp.cvs[0] += 1

		with ThreadPoolExecutor() as pool:
			mods = pool.map(load, mcpack.mod_list)

	try: w = os.get_terminal_size()[0]
	except OSError: w = 132
	for ii, mod in enumerate(mods, 1):
		vers = set(map(operator.itemgetter('gameVersion'), mod['latestFilesIndexes']))
		loaders = {j for f in mod['latestFiles'] for v in mcpack.file_versions(f).values() for j in v if not j[0].isdigit()}
		s = f"\033[1m• {mod['name'].strip()}\033[22m (\033[96m{terminal_link(mod['links']['websiteUrl'], mod['slug'])}\033[39m) \033[2mby {mod['authors'][0]['name']}\033[22m \033[1;{92 if (mcpack.mc_version in vers) else 91 if (vers) else 2}m{f'{min(vers, key=version.parse)}–{max(vers, key=version.parse)}' if (vers) else '?'}\033[m \033[2;{92 if (set(mcpack.loaders) & loaders) else 91}m{' '.join((f'\033[1;4m{j}\033[22;24;2m' if (j in mcpack.loaders) else j) for j in sorted(loaders))}\033[m "
		print(s + f"\033[1;94m({S(', ').join(S(mod['categories'])@['name']).wrap(w-1, loff=len(noesc.sub('', s))+1)})\033[m")
		print(' '*3 + S(mod['summary']).wrap(w, loff=4))
		print()

@apcmd(metavar='<action>')
@aparg('--client', action='store_true', help="Client only")
@aparg('--server', action='store_true', help="Server only")
#@aparg('--beta', action='store_true', help="Allow beta versions")
#@aparg('--alpha', action='store_true', help="Allow alpha and beta versions")
@aparg('--skip-version', help="Mods to skip Minecraft version check")
def update(cargs):
	""" Download/update all mods in the bundle along with their dependencies. """

	mcpack = MCPack.open()

	if (not mcpack.mc_version): exit("Set Minecraft version with `mcpack version' first.")

	cf = CurseForgeAPI()

	print_state(4, "Resolving dependencies...")
	mod_files = Sdict()

	skip_version = (set(mcpack.skip_version) | set(map(str.strip, (cargs.skip_version or '').split(','))))

	with ThreadPoolExecutor() as pool:
		def add_dep(id_): # TODO: conflicts, optionals?
			# TODO:
			#print(f"Mod {id_} doesn't have any{'' if (cargs.alpha) else ' release/beta' if (cargs.beta) else ' release'} versions on the first page."); ok = False
			try: f = mod_files[id_] = first(f for f in sorted(cf.getAddonFiles(id_, gameVersion=mcpack.mc_version), key=operator.itemgetter('id'), reverse=True)
			                                  if (mcpack.loaders is None or any(l in f['gameVersions'] for l in mcpack.loaders))
			                                     and (not cargs.client or 'Client' not in f['gameVersions'] or 'Server' not in f['gameVersions'])
			                                     and (not cargs.server or 'Server' not in f['gameVersions'] or 'Client' not in f['gameVersions']))
			except StopIteration:
				mod = cf.getAddon(id_)
				m = f"mod \033[1m{mod['name'].strip()!r}\033[22m (\033[96m{terminal_link(mod['links']['websiteUrl'], mod['slug'])}\033[39m) does not support \033[1mMinecraft {mcpack.mc_version}\033[22m"
				if (mod['slug'] not in skip_version): print_state(1, f"\033[1;91mError:\033[m {m}."); return False
				else:
					f = mod_files[id_] = first(f for f in sorted(cf.getAddonFiles(id_), key=lambda x: (max((j for v in mcpack.file_versions(x).values() for j in v if j[0].isdigit()), key=version.parse), x['id']), reverse=True)
					                             if any(version.parse(j) <= version.parse(mcpack.mc_version) for v in mcpack.file_versions(f).values() for j in v if j[0].isdigit()))
					print_state(3, f"\033[1;93mWarning:\033[m {m}")
					print_info(3, f"installing it for \033[1m{max((j for v in mcpack.file_versions(f).values() for j in v if j[0].isdigit()), key=version.parse)}\033[22m [\033[3;96m--skip-version\033[23;39m]")

			for i in f['dependencies']:
				if (i['relationType'] in (0, 3)):  # https://docs.curseforge.com/rest-api/#tocS_FileDependency
					pool.submit(add_dep, i['modId'])

			return True

		ok = all(pool.map(add_dep, mcpack.mod_list))
	if (not ok): print_state(1, "Aborting."); exit(1, nolog=True)

	print_state(5, "Mods to install:")
	print(S('  ').join(sorted(cf.getAddon(i)['slug'] for i in mod_files)).wrap(os.get_terminal_size()[0]), end='\n\n')

	print("\033[1m• Dependency tree:")
	def build_deps(x): return {cf.getAddon(i)['name'].strip(): build_deps(j['modId'] for j in mod_files.get(i, {}).get('dependencies', ()) if j['relationType'] in (0, 3)) for i in x}
	NodesTree(build_deps(mcpack.mod_list)).print(root=False, usenodechars=True, indent=1)
	print("\033[m")

	print_state(4, "Downloading mods...")

	fns = set()

	for k, v in mod_files.items():
		mod = cf.getAddon(k)
		print(f"\033[1m• Installing {mod['name'].strip()}\033[22m")
		installed = bool()

		#fn = f"{name}-{mcpack.version_filename(v)}"
		fn = v['fileName']

		if (os.path.exists('Disabled/') and fn in os.listdir('Disabled')):
			print_info(3, "mod is disabled \033[2m(in Disabled/)\033[22m")
			continue

		## TODO FIXME:
		#for i in os.listdir():
		#	m = re.match(r'(.*)-([\d\.]+)_(\d+)\.\w+', i)
		#	if (m is None): continue
		#	if (m[1] != name): continue
		#	if (m[2] != mcpack.mc_version): continue
		#	if (int(m[3]) != v['id']):
		#		print(f"Uninstalling {m[1]} version {m[3]}")
		#		os.remove(i)
		#	else: installed = True
		##

		try:
			with open(fn, 'rb') as f:
				data = f.read()
				for i in v['hashes']:
					match i['algo']:
						case 1: assert (hashlib.sha1(data).hexdigest() == i['value']); break
						case 2: assert (hashlib.md5(data).hexdigest() == i['value']); break
				else: raise WTFException(v['hashes'])
		except Exception: pass
		else: print_info(3, "already installed"); continue

		url = v['downloadUrl']
		if (not url):
			try: url = cf.getAddonFileDownloadUrl(k, v['id'])
			except requests.HTTPError: print_info(1, f"download manually: https://curseforge.com/minecraft/mc-mods/{mod['slug']}/download/{v['id']}"); exit(1)

		with open(fn, 'wb') as f:
			try:
				with requests.get(url, stream=True) as r:
					for c in progiter(r.iter_content(chunk_size=4096), math.ceil(int(r.headers.get('Content-Length'))/4096)):
						f.write(c)
			except: os.remove(fn); raise
		fns.add(fn)
	print()

	print_state(4, "Verifying installation...")

	for i in os.listdir():
		if (os.path.splitext(i)[1] == 'jar' and i not in fns):
			print_info(2, f"Moving {i} to Old/")
			if (not os.path.isdir('Old')): os.mkdir('Old')
			shutil.move(i, os.path.join('Old', i))

		m = re.match(r'(.*)-([\d\.]+)_(\d+)\.\w+', i)
		if (m is None): continue
		if (m[2] != mcpack.mc_version):
			if (input(f"{m[1]} for {m[2]} is probably not compatible with Minecraft {mcpack.mc_version}. Disable? [Y/n] ").strip().casefold() in 'y'):
				if (not os.path.isdir('Disabled')): os.mkdir('Disabled')
				shutil.move(i, os.path.join('Disabled', i))
				print(f"Disabled {m[1]}.")
			continue
	print()

	if (ok): print_state(2, "Update successful.")

@apcmd(metavar='<action>')
#@aparg('--beta', action='store_true', help="Allow beta versions")
#@aparg('--alpha', action='store_true', help="Allow alpha and beta versions")
@aparg('--skip-version', help="Mods to skip Minecraft version check")
def commonver(cargs):
	""" Compute common list of Minecraft versions supported by all mods in the pack. """

	mcpack = MCPack.open()
	cf = CurseForgeAPI()

	print_state(4, "Resolving dependencies...")

	skip_version = (set(mcpack.skip_version) | set(map(str.strip, (cargs.skip_version or '').split(','))))

	versions = dict()
	def add_deps(addonIds): # TODO: conflicts, optionals?
		nonlocal versions
		files = dict()
		for i in addonIds:
			mod = cf.getAddon(i)
			if (mod['slug'] in skip_version): continue
			fl = cf.getAddonFiles(i)
			# TODO:
			#print(f"Mod {i} doesn't have any{'' if (cargs.alpha) else ' release/beta' if (cargs.beta) else ' release'} versions on the first page.")
			versions[i] = {(j, *sorted(l for l in i if not l[0].isdigit())) for f in fl for i in itertools.product(*map(operator.itemgetter(1), sorted((k, v) for k, v in mcpack.file_versions(f).items() if k != 75208))) for j in i if j[0].isdigit()}
		if (not files): return
		add_deps(j['modId'] for i in files.values() for j in i['dependencies'] if j['relationType'] in (0, 3))
	add_deps(mcpack.mod_list)

	print_state(5, "Common Minecraft versions:")
	common = sorted(set.intersection(*versions.values()), key=lambda x: map(version.parse, x))
	if (common): print('  '.join(' '.join(i) for i in common))
	else: print('  '.join(sorted(set.intersection(*({j for i in v for j in i if j[0].isdigit()} for v in versions.values())), key=version.parse)))
	print("\033[m")

@apcmd(metavar='<action>')
@aparg('version', nargs='?')
def version_(cargs):
	""" Get/set Minecraft version for this directory. """

	mcpack = MCPack.open()
	if (cargs.version is None): print(f"Current Minecraft version is {mcpack.mc_version}."); return

	mcpack.mc_version = cargs.version
	mcpack.save()
	print(f"Successfully set Minecraft {mcpack.mc_version} version.")

@apcmd(metavar='<action>')
@aparg('loader', nargs='*')
def loaders(cargs):
	""" Get/set mod loaders for this directory. """

	mcpack = MCPack.open()
	if (not cargs.loader): print(f"Current loaders: {', '.join(sorted(mcpack.loaders or ('none',)))}."); return

	mcpack.loaders = tuple(cargs.loader)
	mcpack.save()
	print(f"Successfully set mod loaders.")

@apcmd(metavar='<action>')
@aparg('file', type=argparse.FileType('r'))
def import_(cargs):
	""" Import modlist from exported file. """

	cf = CurseForgeAPI()

	data = yaml.safe_load(cargs.file)

	mcpack = MCPack.open()

	print("Importing mods")

	if ('mc_version' in data): mcpack.mc_version = data['mc_version']
	mcpack.mod_list += [id for id in (cf.getAddonBySlug(i)['id'] for i in progiter(data['mod_list'])) if id not in mcpack.mod_list]

	mcpack.save()
	print("Import successful.")

@apcmd(metavar='<action>')
@aparg('file', type=argparse.FileType('w'))
def export(cargs):
	""" Export modlist to file. """

	cf = CurseForgeAPI()

	data = dict()

	mcpack = MCPack.open()

	print("Exporting mods")

	if (mcpack.mc_version is not None): data['mc_version'] = mcpack.mc_version
	data['mod_list'] = [cf.getAddon(i)['slug'] for i in progiter(mcpack.mod_list)]

	yaml.safe_dump(data, cargs.file)
	print("Export successful.")

@apmain
def main(cargs):
	try: return cargs.func(cargs)
	#except Exception as ex: exception(ex)
	except KeyboardInterrupt as ex: exit(ex, nolog=True)

if (__name__ == '__main__'): exit(main(nolog=True), nolog=True)

# by Sdore, 2020-26
#   www.sdore.me
