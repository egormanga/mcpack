#!/usr/bin/python3
# MCPack

from packaging import version
from utils.nolog import *
from .config import API_KEY

def print_state(c, t): print(f"\033[1;9{c}m==>\033[0m \033[1m{t}\033[0m")
def print_info(c, t): print(f"   \033[1;9{c}m>\033[0m \033[1m{t}\033[0m")

class CurseForgeAPI:
	api_base_url = "https://api.curseforge.com/v1"
	api_headers = {'User-Agent': None, 'X-API-Key': API_KEY}

	@classmethod
	@lrucachedfunction
	def api_get(cls, path, **kwargs):
		r = requests.get(f"{cls.api_base_url}/{path.lstrip('/')}", headers=cls.api_headers, params=kwargs)
		if (not r.ok): r.raise_for_status()
		return S(r.json()['data'])

	def search(self, name, gameId=432, classId=6, sortField=2, sortOrder='desc', **kwargs):
		return self.api_get('/mods/search', gameId=gameId, classId=classId, searchFilter=name, sortField=sortField, sortOrder=sortOrder, **kwargs)

	def getAddon(self, addonId):
		return self.api_get(f"/mods/{addonId}")

	def getAddonBySlug(self, slug):
		return first(i for i in self.search(slug) if i['slug'] == slug)

	def getAddonFiles(self, addonId, gameVersion=None, **kwargs):
		if (gameVersion is not None): parseargs(kwargs, gameVersion=gameVersion)
		return self.api_get(f"/mods/{addonId}/files", **kwargs)

	def getAddonFileInfo(self, addonId, fileId):
		return self.api_get(f"/mods/{addonId}/file/{fileId}")

class MCPack(Slots):
	mc_version: None
	mod_list: list
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
		json.dump({i: getattr(self, i) for i in self.__slots__}, open(file, 'w') if (isinstance(file, str)) else file)

def file_versions(file: dict): return tuple(v for i in file.get('sortableGameVersions', ()) if (v := i['gameVersion']) and v[0].isdigit())

@apcmd(metavar='<action>')
@aparg('name')
def add(cargs):
	""" Add a mod to the bundle. """

	mcpack = MCPack.open()

	cf = CurseForgeAPI()

	res = cf.search(cargs.name)
	l = res #sorted(res, key=lambda x: (x['slug'] != cargs.name, -x['popularityScore'], x['name']))
	w = os.get_terminal_size()[0]
	for ii, i in enumerate(l, 1):
		s = f"\033[7;33m{ii}\033[0m \033[1m{i['name'].strip()}\033[0m (\033]8;;{i['links']['websiteUrl']}\033\\{i['slug']}\033]8;;\033\\) \033[2mby {i['authors'][0]['name']}\033[0m \033[1;92m{max((v for f in i['latestFiles'] for v in file_versions(f)), key=version.parse, default='?')}\033[0m \033[1;7;93m({int(i['downloadCount'])})\033[0m "
		print(s + f"\033[1;34m({S(', ').join(S(i['categories'])@['name']).wrap(w-1, loff=len(noesc.sub('', s))+1)})\033[0m" + ' \033[1;33;7m[added]\033[0m'*(i['id'] in mcpack.mod_list))
		print(' '*(len(Sint(ii))+3) + S(i['summary']).wrap(w, loff=len(Sint(ii))+4))
		print()

	s = "Select mods to add (e.g. 1 2 3-5)"
	print_state(3, s)
	print_state(3, '-'*len(s))
	q = input('\1\033[1;93m\2==>\1\033[0m\2 ')
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

	try: a = first(i for i in cf.search(cargs.name) if i['id'] in mcpack.mod_list and (cargs.name.strip() == i['slug'] or cargs.name.strip().casefold() == i['name'].strip().casefold()))
	except StopIteration: print_state(1, "No such mod."); return
	else: ii = mcpack.mod_list.index(a['id'])

	fl = cf.getAddonFiles(a['id'], gameVersion=mcpack.mc_version)
	try: f = first(f for f in sorted(fl, key=operator.itemgetter('id'), reverse=True) if f['downloadUrl'] is not None)
	except StopIteration: pass
	else:
		name = a['name'].strip()
		r = requests.get(f['downloadUrl'], stream=True)
		vers = file_versions(f['latestFiles'][0])
		fn = f"{name}-{mcpack.mc_version if (mcpack.mc_version in vers) else max(vers, key=version.parse)}_{f['id']}.{r.url.split('.')[-1]}"
		if (os.path.exists(fn)):
			if (not os.path.isdir('Removed')): os.mkdir('Removed')
			shutil.move(fn, os.path.join('Removed', fn))

	del mcpack.mod_list[ii]
	mcpack.save()

	print_state(2, f"Removed '{a['name'].strip()}'.")

@apcmd(metavar='<action>')
def list(cargs):
	""" List mods in bundle. """

	mcpack = MCPack.open()

	cf = CurseForgeAPI()

	l = mcpack.mod_list
	w = os.get_terminal_size()[0]
	for ii, i in enumerate(l, 1):
		i = cf.getAddon(i)
		s = f"\033[1m• {i['name'].strip()}\033[0m (\033]8;;{i['links']['websiteUrl']}\033\\{i['slug']}\033]8;;\033\\) \033[2mby {i['authors'][0]['name']}\033[0m "
		print(s + f"\033[1;94m({S(', ').join(S(i['categories'])@['name']).wrap(w-1, loff=len(noesc.sub('', s))+1)})\033[0m")
		print(' '*3 + S(i['summary']).wrap(w, loff=4))
		print()

@apcmd(metavar='<action>')
#@aparg('--beta', action='store_true', help="Allow beta versions")
#@aparg('--alpha', action='store_true', help="Allow alpha and beta versions")
@aparg('--skip-version', action='store_true', help="Skip Minecraft version check")
def update(cargs):
	""" Download/update all mods in the bundle along with their dependencies. """

	mcpack = MCPack.open()

	if (not mcpack.mc_version): exit("Set Minecraft version with `mcpack version' first.")

	cf = CurseForgeAPI()

	print_state(4, "Resolving dependencies...")
	mod_files = Sdict()

	ok = True
	def add_deps(addonIds): # TODO: conflicts, optionals?
		nonlocal ok
		files = dict()

		for i in addonIds:
			fl = cf.getAddonFiles(i, gameVersion=mcpack.mc_version)
			# TODO:
			#print(f"Mod {i} doesn't have any{'' if (cargs.alpha) else ' release/beta' if (cargs.beta) else ' release'} versions on the first page."); ok = False
			try: files[i] = first(f for f in sorted(fl, key=operator.itemgetter('id'), reverse=True) if f['downloadUrl'] is not None)
			except StopIteration:
				m = f"mod \033[1m'{cf.getAddon(i)['name'].strip()}'\033[0m does not support \033[1mMinecraft {mcpack.mc_version}\033[0m."
				if (not cargs.skip_version): print_state(1, f"\033[1;91mError:\033[0m {m}"); ok = False; continue
				else:
					print_state(3, f"\033[1;93mWarning:\033[0m {m}")
					fl = cf.getAddonFiles(i)
					files[i] = first(f for f in sorted(fl, key=lambda x: (max(file_versions(x), key=version.parse), x['id']), reverse=True) if any(version.parse(k) <= version.parse(mcpack.mc_version) for k in file_versions(f)) and f['downloadUrl'] is not None)
					print_state(3, f"\033[0m(installing for {max(file_versions(files[i]), key=version.parse)}) [--skip-version]")

		if (not files): return
		mod_files.update(files)
		add_deps(j['modId'] for i in files.values() for j in i['dependencies'])

	add_deps(mcpack.mod_list)
	if (not ok): print_state(1, "Aborting."); exit(1, nolog=True)

	print_state(5, "Mods to install:")
	print(S('  ').join(sorted(cf.getAddon(i)['slug'] for i in mod_files)).wrap(os.get_terminal_size()[0]), end='\n\n')

	print("\033[1m• Dependency tree:")
	def build_deps(x): return {cf.getAddon(i)['name'].strip(): build_deps(j['modId'] for j in mod_files[i]['dependencies']) for i in x}
	NodesTree(build_deps(mcpack.mod_list)).print(root=False, usenodechars=True, indent=1)
	print("\033[0m")

	print_state(4, "Downloading mods...")

	fns = set()

	for k, v in mod_files.items():
		name = cf.getAddon(k)['name'].strip()
		print(f"\033[1m• Installing {name}\033[0m")
		installed = bool()

		for i in os.listdir():
			if (os.path.exists('Disabled/') and i in os.listdir('Disabled')):
				print_info(3, "mod is disabled \033[2m(in Disabled/)\033[0m")
				continue
			m = re.match(r'(.*)-([\d\.]+)_(\d+)\.\w+', i)
			if (m is None): continue
			if (m[1] != name): continue
			if (m[2] != mcpack.mc_version): continue
			if (int(m[3]) != v['id']):
				print(f"Uninstalling {m[1]} version {m[3]}")
				os.remove(i)
			else: installed = True

		if (installed): print_info(3, "already installed"); continue

		r = requests.get(v['downloadUrl'], stream=True)
		vers = file_versions(v)
		fn = f"{name}-{mcpack.mc_version if (mcpack.mc_version in vers) else max(vers, key=version.parse)}_{v['id']}.{r.url.split('.')[-1]}"
		fns.add(fn)

		f = open(fn, 'wb')
		for c in progiter(r.iter_content(chunk_size=4096), math.ceil(int(r.headers.get('Content-Length'))/4096)):
			f.write(c)
		f.close()
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
def commonver(cargs):
	""" Compute common list of Minecraft versions supported by all mods in the pack. """

	mcpack = MCPack.open()
	cf = CurseForgeAPI()

	print_state(4, "Resolving dependencies...")

	versions = None

	def add_deps(addonIds): # TODO: conflicts, optionals?
		nonlocal versions
		files = dict()
		for i in addonIds:
			fl = cf.getAddonFiles(i)
			# TODO:
			#print(f"Mod {i} doesn't have any{'' if (cargs.alpha) else ' release/beta' if (cargs.beta) else ' release'} versions on the first page."); ok = False
			s = {k for j in fl for k in file_versions(j)}
			if (versions is None): versions = s
			else: versions &= s
		if (not files): return
		add_deps(j['modId'] for i in files.values() for j in i['dependencies'])

	add_deps(mcpack.mod_list)

	print_state(5, "Common Minecraft versions:")
	print('  '.join(sorted(versions, key=version.parse)))
	print("\033[0m")

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

# by Sdore, 2020-22
#   www.sdore.me
