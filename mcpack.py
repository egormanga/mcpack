#!/usr/bin/python3
# MCPack

from utils.nolog import *

def print_state(c, t): print(f"\033[1;9{c}m==>\033[0m \033[1m{t}\033[0m")
def print_info(c, t): print(f"   \033[1;9{c}m>\033[0m \033[1m{t}\033[0m")

class TwitchAddonAPI:
	api_base_url = "https://addons-ecs.forgesvc.net/api/v2/addon"
	api_headers = {'User-Agent': None}

	@classmethod
	@cachedfunction
	def api_get(cls, path, **kwargs): return S(requests.get(cls.api_base_url+path, headers=cls.api_headers, params=kwargs).json())

	def search(self, name):
		return self.api_get('/search', gameId=432, searchFilter=name)@{'categorySection': lambda x: x['id'] == 8}

	def getAddon(self, addonId):
		return self.api_get(f"/{addonId}")

	def getAddonBySlug(self, slug):
		return first(self.search(slug)@{'slug': (slug,)})

	def getAddonFiles(self, addonId):
		return self.api_get(f"/{addonId}/files")

	def getAddonFileInfo(self, addonId, fileId):
		return self.api_get(f"/{addonId}/file/{fileId}")

class MCPack(metaclass=SlotsMeta):
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

@apcmd(metavar='<action>')
@aparg('name')
def add(cargs):
	""" Add a mod to the bundle. """

	mcpack = MCPack.open()

	cf = TwitchAddonAPI()

	res = cf.search(cargs.name)
	l = sorted(res, key=lambda x: (x['slug'] != cargs.name, -x['popularityScore'], x['name']))
	w = os.get_terminal_size()[0]
	for ii, i in enumerate(l, 1):
		s = f"\033[7;33m{ii}\033[0m \033[1m{i['name']}\033[0m ({i['slug']}) \033[2mby {i['authors'][0]['name']}\033[0m "
		print(s + f"\033[1;34m({S(', ').join(S(i['categories'])@['name']).wrap(w-1, loff=len(noesc.sub('', s))+1)})\033[0m" + ' \033[1;33;7m[added]\033[0m'*(i['id'] in mcpack.mod_list))
		print(' '*(len(Sint(ii))+3) + S(i['summary']).wrap(w, loff=len(Sint(ii))+4))

	s = "Select mods to add (e.g. 1 2 3-5)"
	print_state(3, s)
	print_state(3, '-'*len(s))
	sel = [j for i in re.findall(r'(\d+)(?:-(\d+))?', input('\1\033[1;93m\2==>\1\033[0m\2 ')) for j in (range(int(i[0]), int(i[1])+1) if (i[1]) else (int(i[0]),))]
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

	cf = TwitchAddonAPI()

	for ii, i in enumerate(mcpack.mod_list):
		i = cf.getAddon(i)
		if (cargs.name.casefold() in (i['slug'], i['name'].casefold())): break
	else: print_state(1, "No such mod."); return

	del mcpack.mod_list[ii]
	mcpack.save()

	print_state(2, f"Removed '{i['name']}'.")

@apcmd(metavar='<action>')
def list(cargs):
	""" List mods in bundle. """

	mcpack = MCPack.open()

	cf = TwitchAddonAPI()

	l = mcpack.mod_list
	w = os.get_terminal_size()[0]
	for ii, i in enumerate(l, 1):
		i = cf.getAddon(i)
		s = f"\033[1m• {i['name']}\033[0m ({i['slug']}) \033[2mby {i['authors'][0]['name']}\033[0m "
		print(s + f"\033[1;94m({S(', ').join(S(i['categories'])@['name']).wrap(w-1, loff=len(noesc.sub('', s))+1)})\033[0m")
		print(' '*3 + S(i['summary']).wrap(w, loff=4))

@apcmd(metavar='<action>')
#@aparg('--beta', action='store_true', help="Allow beta versions")
#@aparg('--alpha', action='store_true', help="Allow alpha and beta versions")
def update(cargs):
	""" Download/update all mods in the bundle along with their dependencies. """

	mcpack = MCPack.open()

	if (not mcpack.mc_version): exit("Set Minecraft version with `mcpack version' first.")

	cf = TwitchAddonAPI()

	print_state(4, "Resolving dependencies...")
	mod_files = Sdict()

	ok = True
	def add_deps(addonIds): # TODO: conflicts, optionals?
		nonlocal ok
		files = dict()
		for i in addonIds:
			fl = cf.getAddonFiles(i)
			# TODO:
			#print(f"Mod {i} doesn't have any{'' if (cargs.alpha) else ' release/beta' if (cargs.beta) else ' release'} versions on the first page."); ok = False
			try: files[i] = first(j for j in sorted(fl, key=operator.itemgetter('id'), reverse=True) if mcpack.mc_version in j['gameVersion'])
			except StopIteration: print_state(1, f"\033[1;91mError:\033[0m mod \033[1m'{cf.getAddon(i)['name']}'\033[0m does not support \033[1mMinecraft {mcpack.mc_version}\033[0m."); ok = False; continue
		if (not files): return
		mod_files.update(files)
		add_deps(j['addonId'] for i in files.values() for j in i['dependencies'] if j['type'] == 3) # TODO: 'type'

	add_deps(mcpack.mod_list)
	if (not ok): print_state(1, "Aborting."); exit(1, nolog=True)

	print_state(5, "Mods to install:")
	print(S(' ').join(sorted(cf.getAddon(i)['slug'] for i in mod_files)).wrap(os.get_terminal_size()[0]), end='\n\n')

	def build_deps(x): return {cf.getAddon(i)['name']: build_deps(j['addonId'] for j in mod_files[i]['dependencies'] if j['type'] == 3) for i in x}

	print("\033[1m• Dependency tree:")
	NodesTree(build_deps(mcpack.mod_list)).print(root=False, usenodechars=True, indent=1)
	print("\033[0m")

	print_state(4, "Downloading mods...")

	for k, v in mod_files.items():
		name = cf.getAddon(k)['name']
		print(f"\033[1m• Installing {name}\033[0m")
		installed = bool()
		for i in os.listdir():
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
		fn = f"{name}-{mcpack.mc_version}_{v['id']}.{r.url.split('.')[-1]}"
		f = open(fn, 'wb')
		for c in progiter(r.iter_content(chunk_size=4096), math.ceil(int(r.headers.get('Content-Length'))/4096)):
			f.write(c)
		f.close()
	print()

	print_state(4, "Verifying installation...")

	for i in os.listdir():
		m = re.match(r'(.*)-([\d\.]+)_(\d+)\.\w+', i)
		if (m is None): continue
		if (m[2] != mcpack.mc_version):
			if (input(f"{m[1]} for {m[2]} is probably not compatible with Minecraft {mcpack.mc_version}. Disable? [Y/n] ").strip().casefold() in 'y'):
				if (not os.path.isdir('Disabled')): os.mkdir('Disabled')
				shutil.move(i, 'Disabled/'+i)
				print(f"Disabled {m[1]}.")
			continue
	print()

	if (ok): print_state(2, "Update successful.")

@apcmd(metavar='<action>')
@aparg('version', nargs='?')
def version(cargs):
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

	cf = TwitchAddonAPI()

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

	cf = TwitchAddonAPI()

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
	except Exception as ex: exception(ex)
	except KeyboardInterrupt as ex: exit(ex, nolog=True)

if (__name__ == '__main__'): exit(main(nolog=True), nolog=True)

# by Sdore, 2020
