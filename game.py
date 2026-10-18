"""RTS MÉDIÉVAL v6 - logique du jeu (sans interface) : 3 factions, technologies, capacités, campagne, tutoriels, réseau."""
import copy
import heapq
import math
import random

MAP_W, MAP_H = 2400, 1600
POP_MAX = 60
CELL = 40
GW, GH = MAP_W // CELL, MAP_H // CELL
NB = [(1, 0, 1.0), (-1, 0, 1.0), (0, 1, 1.0), (0, -1, 1.0),
      (1, 1, 1.414), (1, -1, 1.414), (-1, 1, 1.414), (-1, -1, 1.414)]

UNITS = {
    'worker': dict(label='Récolteur', hp=40, speed=90, dmg=3, rng=18, cd=1.0, cost=(50, 0), time=5, r=11, armor=0),
    'soldier': dict(label='Soldat', hp=110, speed=78, dmg=12, rng=24, cd=0.9, cost=(50, 25), time=8, r=13, armor=2),
    'archer': dict(label='Archer', hp=50, speed=85, dmg=9, rng=140, cd=1.1, cost=(50, 30), time=8, r=11, armor=0),
    'knight': dict(label='Cavalier', hp=120, speed=135, dmg=16, rng=26, cd=1.0, cost=(80, 60), time=12, r=16, armor=1),
    'healer': dict(label='Soigneur', hp=55, speed=80, dmg=2, rng=18, cd=1.4, cost=(60, 60), time=10, r=11, armor=0, heal=7),
    'heavy': dict(label='Unité lourde', hp=220, speed=60, dmg=26, rng=28, cd=1.8, cost=(120, 80), time=16, r=18, armor=2, bmult=1.6),
}
BUILDINGS = {
    'hq': dict(label='QG', hp=1000, r=58, cost=(0, 0), time=0, makes=['worker'], req=[]),
    'barracks': dict(label='Caserne', hp=500, r=44, cost=(150, 50), time=14, makes=['soldier', 'archer'], req=[]),
    'stable': dict(label='Écurie', hp=500, r=44, cost=(180, 100), time=16, makes=['knight'], req=['barracks']),
    'depot': dict(label='Dépôt', hp=260, r=34, cost=(100, 0), time=8, makes=[], req=[]),
    'tower': dict(label='Tour', hp=320, r=26, cost=(120, 60), time=12, makes=[], dmg=11, rng=200, cd=1.2, req=[]),
    'forge': dict(label='Forge', hp=420, r=42, cost=(150, 100), time=16, makes=[], req=['barracks']),
    'temple': dict(label='Temple', hp=380, r=40, cost=(160, 120), time=18, makes=['healer'], req=['barracks']),
    'sanctum': dict(label='Sanctuaire', hp=520, r=46, cost=(220, 160), time=22, makes=['heavy'], req=['forge']),
}
BUILD_ORDER = ('barracks', 'stable', 'depot', 'tower', 'forge', 'temple', 'sanctum')
BONUS = {('soldier', 'knight'): 1.5, ('knight', 'archer'): 1.6, ('archer', 'soldier'): 1.5,
         ('archer', 'heavy'): 1.4, ('heavy', 'soldier'): 1.3, ('knight', 'healer'): 1.3}
BUILD_MULT = {'archer': 0.4, 'knight': 0.8}
MIL = ['soldier', 'archer', 'knight', 'heavy', 'healer']
MELEE = ['soldier', 'knight', 'heavy']
PTYPE = {'kingdom': 'arrow', 'horde': 'bolt', 'sylvan': 'orb'}
AI_GATHER = (0.8, 1.0, 1.3)
AI_THINK = (1.4, 1.0, 0.6)
AI_GRACE = (300, 210, 140)
DIFF_NAMES = ('Facile', 'Normal', 'Difficile')

FACTIONS = {
    'kingdom': dict(
        name="Royaume d'Aurèle", short='Royaume',
        trait='Équilibré. Bâtiments robustes, catapultes dévastatrices contre les bases.',
        units=dict(worker='Paysan', soldier='Fantassin', archer='Archer', knight='Chevalier', healer='Prêtre', heavy='Catapulte'),
        blds=dict(hq='Château', barracks='Caserne', stable='Écurie', depot='Grenier', tower='Tour de guet',
                  forge='Forge royale', temple='Chapelle', sanctum='Atelier de siège'),
        ability=dict(name='Ordre royal', desc='+30 % de dégâts et +15 % de vitesse pour toute l\'armée pendant 18 s.', dur=18, cd=120, icon='ab_k'),
        gather=1.0),
    'horde': dict(
        name='Horde de Gorak', short='Horde',
        trait='Brutale et bon marché. Grunts puissants, loups très rapides, ogres écrasants. Bâtiments fragiles.',
        units=dict(worker='Péon', soldier='Grunt', archer='Chasseur', knight='Chevaucheur de loup', healer='Chaman', heavy='Ogre'),
        blds=dict(hq='Forteresse', barracks='Fosse de guerre', stable='Tanière', depot='Entrepôt', tower='Tour de crânes',
                  forge='Forge de guerre', temple='Hutte du chaman', sanctum='Fosse des ogres'),
        ability=dict(name='Fureur sanguinaire', desc='+50 % de cadence d\'attaque et +20 % de vitesse pendant 14 s.', dur=14, cd=110, icon='ab_h'),
        gather=0.9),
    'sylvan': dict(
        name="Sylve d'Elenwë", short='Sylve',
        trait='Précise et agile. Archers à longue portée, tours redoutables, Ents régénérants.',
        units=dict(worker='Cueilleur', soldier='Garde-lame', archer='Rôdeur', knight='Cavalier-cerf', healer='Druide', heavy='Ent'),
        blds=dict(hq='Arbre-cité', barracks='Pavillon des lames', stable='Clairière', depot='Grenier', tower='Tour-fleur',
                  forge='Bosquet ancestral', temple='Puits de lune', sanctum='Sanctuaire des Ents'),
        ability=dict(name='Souffle de la forêt', desc='Soigne 45 % des PV de toute l\'armée, puis régénération pendant 12 s.', dur=12, cd=120, icon='ab_s'),
        gather=1.15),
}

# ----------------------------------------------------------------------------- ARBRE TECHNOLOGIQUE
# effets : ('u', types, stat, 'add'|'mul', v)  ('b', None, 'hp', 'mul', v)  ('g', None, 'gather', 'add', v)
#          ('a', None, 'cd', 'mul', v)  ('h', None, 'heal', 'mul', v)
TECHS = {
    'eco1': dict(bld='hq', cost=(100, 50), time=25, req=[], icon='t_coin', fx=[('g', None, 'gather', 'add', .15)]),
    'eco2': dict(bld='hq', cost=(200, 120), time=40, req=['eco1'], icon='t_coin', fx=[('g', None, 'gather', 'add', .2)]),
    'walls': dict(bld='hq', cost=(150, 80), time=35, req=[], icon='t_tower', fx=[('b', None, 'hp', 'mul', 1.25)]),
    'wpn1': dict(bld='forge', cost=(140, 100), time=30, req=[], icon='t_sword', fx=[('u', MELEE, 'dmg', 'add', 3)]),
    'wpn2': dict(bld='forge', cost=(260, 200), time=50, req=['wpn1'], icon='t_sword', fx=[('u', MELEE, 'dmg', 'add', 4)]),
    'arm1': dict(bld='forge', cost=(140, 100), time=30, req=[], icon='t_shield', fx=[('u', ['soldier', 'archer', 'knight', 'heavy'], 'armor', 'add', 1)]),
    'arm2': dict(bld='forge', cost=(260, 200), time=50, req=['arm1'], icon='t_shield',
                 fx=[('u', ['soldier', 'archer', 'knight', 'heavy'], 'armor', 'add', 1), ('u', ['soldier', 'archer', 'knight', 'heavy'], 'hp', 'mul', 1.1)]),
    'rng1': dict(bld='forge', cost=(160, 120), time=35, req=[], icon='t_bow', fx=[('u', ['archer'], 'rng', 'add', 25), ('u', ['archer'], 'dmg', 'add', 3)]),
    'speed1': dict(bld='temple', cost=(180, 120), time=35, req=[], icon='t_boot', fx=[('u', ['soldier', 'archer', 'knight', 'heavy', 'healer', 'worker'], 'speed', 'mul', 1.08)]),
    'heal1': dict(bld='temple', cost=(150, 150), time=30, req=[], icon='t_heart', fx=[('h', None, 'heal', 'mul', 1.5), ('u', ['healer'], 'hp', 'mul', 1.3)]),
    'ward': dict(bld='temple', cost=(200, 200), time=45, req=[], icon='t_magic', fx=[('a', None, 'cd', 'mul', .65)]),
    'heavy1': dict(bld='sanctum', cost=(250, 220), time=50, req=[], icon='t_hammer', fx=[('u', ['heavy'], 'hp', 'mul', 1.25), ('u', ['heavy'], 'dmg', 'add', 6)]),
    'heavy2': dict(bld='sanctum', cost=(350, 300), time=70, req=['heavy1'], icon='t_hammer', fx=[('u', ['heavy'], 'armor', 'add', 2), ('u', ['heavy'], 'speed', 'mul', 1.12)]),
}
TECH_NAMES = {
    'kingdom': dict(eco1=('Charrues de fer', 'Les récolteurs rapportent 15 % de ressources en plus.'),
                    eco2=('Greniers royaux', 'Encore +20 % de ressources récoltées.'),
                    walls=('Remparts de pierre', 'Tous vos bâtiments ont +35 % de PV.'),
                    wpn1=('Lames trempées', 'Soldats, cavaliers et unités lourdes : +3 dégâts.'),
                    wpn2=('Acier de Damas', 'Mêlée : +4 dégâts supplémentaires.'),
                    arm1=('Cottes de mailles', 'Armure +1 pour toute l\'armée.'),
                    arm2=('Armures de plates', 'Armure +1 et +10 % de PV.'),
                    rng1=('Arbalètes lourdes', 'Archers : +25 de portée, +3 dégâts.'),
                    speed1=('Routes pavées', 'Toutes les unités vont 8 % plus vite.'),
                    heal1=('Bénédiction', 'Les prêtres soignent 50 % plus vite et ont +30 % de PV.'),
                    ward=('Ordre suprême', 'Capacité du Royaume : recharge réduite de 35 %.'),
                    heavy1=('Engins perfectionnés', 'Catapultes : +25 % de PV, +6 dégâts.'),
                    heavy2=('Ingénierie royale', 'Catapultes : armure +2 et +12 % de vitesse.')),
    'horde': dict(eco1=('Pillage organisé', 'Les récolteurs rapportent 15 % de ressources en plus.'),
                  eco2=('Butin des clans', 'Encore +20 % de ressources récoltées.'),
                  walls=('Palissades hérissées', 'Tous vos bâtiments ont +25 % de PV.'),
                  wpn1=('Haches affûtées', 'Grunts, loups et ogres : +4 dégâts.'),
                  wpn2=('Haches de sang', 'Mêlée : +4 dégâts supplémentaires.'),
                  arm1=('Peaux épaisses', 'Armure +1 et +12 % de PV pour toute l\'armée.'),
                  arm2=('Armures d\'os', 'Armure +1 et +10 % de PV.'),
                  rng1=('Javelots barbelés', 'Chasseurs : +25 de portée, +3 dégâts.'),
                  speed1=('Course sauvage', 'Toutes les unités vont 12 % plus vite.'),
                  heal1=('Rituels de guérison', 'Les chamans soignent 50 % plus vite et ont +30 % de PV.'),
                  ward=('Cri de guerre', 'Capacité de la Horde : recharge réduite de 35 %.'),
                  heavy1=('Ogres enragés', 'Ogres : +25 % de PV, +6 dégâts.'),
                  heavy2=('Ogres cuirassés', 'Ogres : armure +2 et +12 % de vitesse.')),
    'sylvan': dict(eco1=('Cueillette bénie', 'Les récolteurs rapportent 15 % de ressources en plus.'),
                   eco2=('Sève nourricière', 'Encore +20 % de ressources récoltées.'),
                   walls=('Ronces protectrices', 'Tous vos bâtiments ont +25 % de PV.'),
                   wpn1=('Lames lunaires', 'Gardes-lames, cerfs et Ents : +3 dégâts.'),
                   wpn2=('Lames d\'aube', 'Mêlée : +4 dégâts supplémentaires.'),
                   arm1=('Écorce vivante', 'Armure +1 pour toute l\'armée.'),
                   arm2=('Armures de feuillage', 'Armure +1 et +10 % de PV.'),
                   rng1=('Flèches lunaires', 'Rôdeurs : +40 de portée, +3 dégâts.'),
                   speed1=('Sentiers secrets', 'Toutes les unités vont 12 % plus vite.'),
                   heal1=('Eaux de vie', 'Les druides soignent 50 % plus vite et ont +30 % de PV.'),
                   ward=('Harmonie sylvestre', 'Capacité de la Sylve : recharge réduite de 35 %.'),
                   heavy1=('Racines éveillées', 'Ents : +25 % de PV, +6 dégâts.'),
                   heavy2=('Gardiens millénaires', 'Ents : armure +2 et +12 % de vitesse.')),
}
# variantes d'effets propres à chaque faction
TECH_FX = {
    'kingdom': dict(walls=[('b', None, 'hp', 'mul', 1.35)]),
    'horde': dict(wpn1=[('u', MELEE, 'dmg', 'add', 4)], arm1=[('u', ['soldier', 'archer', 'knight', 'heavy'], 'armor', 'add', 1),
                                                              ('u', ['soldier', 'archer', 'knight', 'heavy'], 'hp', 'mul', 1.12)],
                  speed1=[('u', ['soldier', 'archer', 'knight', 'heavy', 'healer', 'worker'], 'speed', 'mul', 1.12)]),
    'sylvan': dict(rng1=[('u', ['archer'], 'rng', 'add', 40), ('u', ['archer'], 'dmg', 'add', 3)],
                   speed1=[('u', ['soldier', 'archer', 'knight', 'heavy', 'healer', 'worker'], 'speed', 'mul', 1.12)]),
}


def tech_info(fac, tid):
    """(nom, description, coût, durée, bâtiment, prérequis, icône) d'une technologie pour une faction."""
    t = TECHS[tid]
    nm, ds = TECH_NAMES[fac][tid]
    icon = t['icon']
    if icon == 't_hammer':
        icon = {'kingdom': 't_hammer', 'horde': 't_flame', 'sylvan': 't_leaf'}[fac]
    return nm, ds, t['cost'], t['time'], t['bld'], t['req'], icon


def make_stats(fac):
    f = FACTIONS[fac]
    u, b = copy.deepcopy(UNITS), copy.deepcopy(BUILDINGS)
    for k, v in f['units'].items():
        u[k]['label'] = v
    for k, v in f['blds'].items():
        b[k]['label'] = v
    if fac == 'kingdom':
        for d in b.values():
            d['hp'] = int(d['hp'] * 1.15)
        b['tower']['dmg'] += 2
        u['heavy'].update(hp=140, dmg=34, rng=230, cd=2.4, speed=52, armor=0, bmult=2.6, cost=(130, 90), time=16)
        u['healer'].update(heal=7)
    elif fac == 'horde':
        u['soldier'].update(hp=125, dmg=14, cost=(40, 15))
        u['worker'].update(cost=(40, 0), speed=95)
        u['knight'].update(speed=150, hp=110)
        u['archer'].update(hp=40, rng=120)
        u['heavy'].update(hp=260, dmg=30, rng=30, cd=1.5, speed=62, armor=3, bmult=1.6, cost=(110, 70), time=15)
        u['healer'].update(heal=6, hp=50)
        for d in b.values():
            d['hp'] = int(d['hp'] * .85)
            d['time'] = d['time'] * .85
    elif fac == 'sylvan':
        u['archer'].update(rng=170, dmg=11, cost=(50, 35))
        u['soldier'].update(hp=95)
        u['knight'].update(speed=145, dmg=14)
        b['tower'].update(rng=230, dmg=14)
        u['heavy'].update(hp=300, dmg=24, rng=36, cd=1.7, speed=54, armor=4, bmult=1.8, cost=(130, 100), time=17, regen=2.0)
        u['healer'].update(heal=8, hp=50)
        for d in b.values():
            d['hp'] = int(d['hp'] * .9)
    for d in u.values():
        d['base_hp'] = d['hp']
    return u, b


def dist(ax, ay, bx, by):
    return math.hypot(ax - bx, ay - by)


class Res:
    def __init__(self, kind, x, y, amount, id=0):
        self.kind, self.x, self.y, self.amount, self.max, self.id = kind, x, y, amount, amount, id
        self.r = 14 if kind == 'wood' else 16


class Ent:
    def __init__(self, kind, team, x, y, d, building=False, done=True, id=0):
        self.d = d
        self.kind, self.team, self.x, self.y, self.b, self.id = kind, team, x, y, building, id
        self.tx, self.ty = x, y
        self.maxhp = d['hp']
        self.hp = self.maxhp if done else self.maxhp * 0.2
        self.r = d['r']
        self.dead = False
        self.mode = 'idle'
        self.dest = None
        self.target = None
        self.resume = None
        self.prev = None
        self.auto = False
        self.home = (x, y)
        self.cd = 0.0
        self.flash = 0.0
        self.carry = 0
        self.ctype = None
        self.hs = 'go'
        self.gt = 0.0
        self.st = 0.0
        self.lr = 1e9
        self.ang = random.uniform(-3, 3)
        self.moving = False
        self.working = False
        self.built = done
        self.bt = 0.0
        self.queue = []
        self.qt = 0.0
        self.rally = None
        self.research = None
        self.rt = 0.0
        self.hl = 0.0


class Game:
    def __init__(self):
        self.diff = 1
        self.reset()

    # ------------------------------------------------------------ création de partie
    def reset(self, fac0='kingdom', fac1='horde', setup=None, seed=None, me=0, ai_teams=(1,), remote=False):
        self.rng = random.Random(seed)
        self.setup = setup or {}
        self.fac = {0: fac0, 1: fac1}
        self.ust, self.bst = {}, {}
        for t in (0, 1):
            self.ust[t], self.bst[t] = make_stats(self.fac[t])
        self.me, self.ai_teams, self.remote = me, list(ai_teams), remote
        self.ents, self.res, self.rocks, self.fx, self.fx_out = [], [], [], [], []
        self.by_id, self.rid = {}, {}
        self.nid = 1
        self.stock = {t: {'wood': 200, 'ore': 100} for t in (0, 1)}
        self.gathered = {0: 0, 1: 0}
        self.kills = {0: 0, 1: 0}
        self.techs = {0: set(), 1: set()}
        self.gmult = {0: 1.0, 1: 1.0}
        self.abmul = {0: 1.0, 1: 1.0}
        self.healmul = {0: 1.0, 1: 1.0}
        self.abcd = {0: 0.0, 1: 0.0}
        self.buff = {0: 0.0, 1: 0.0}
        self.flags, self.events, self.corpses = set(), [], []
        self.step_i, self.steps_done = 0, 0
        self.bases = {0: (320, 1250), 1: (2080, 350)}
        self.cam = [0, MAP_H - 640]
        self.sel, self.placing, self.drag = [], None, None
        self.over, self.winner, self.reason = None, None, ''
        self.paused, self.amove = False, False
        self.time = 0.0
        self.msg, self.msg_t = '', 0.0
        self.obst = []
        self.outbox = []
        self.record_fx = False
        self.mission = self.norm_mission(self.setup.get('mission'))
        aip = self.setup.get('ai', {})
        self.aist = {t: dict(t=0.0, wave_n=aip.get('wave_n', [6, 5, 4][self.diff]), wave=set(), wave_size=0,
                             think=aip.get('think', AI_THINK[self.diff]), grace=aip.get('grace', AI_GRACE[self.diff]))
                     for t in (0, 1)}
        if 'res' in self.setup:
            self.stock[0].update(wood=self.setup['res'][0], ore=self.setup['res'][1])
        if 'e_res' in self.setup:
            self.stock[1].update(wood=self.setup['e_res'][0], ore=self.setup['e_res'][1])
        for t, (bx, by) in self.bases.items():
            s = 1 if t == 0 else -1
            self.add(self.make('hq', t, bx, by, True))
            for i in range(3):
                self.spawn('worker', t, bx - 40 + i * 24, by + 75 * s)
            self.spawn('soldier', t, bx + 50, by + 75 * s)
        for _ in range(500):
            if len(self.rocks) >= 24:
                break
            x, y, r = self.rng.randint(100, MAP_W - 100), self.rng.randint(100, MAP_H - 100), self.rng.randint(20, 42)
            if all(dist(x, y, bx, by) > 330 for bx, by in self.bases.values()) and self.free(x, y, r, 40):
                self.rocks.append((x, y, r))
        for t, (bx, by) in self.bases.items():
            s = 1 if t == 0 else -1
            self.patch('wood', bx + 250 * s, by - 90 * s, 8, 80, 300)
            self.patch('ore', bx - 60 * s, by - 240 * s, 4, 55, 450)
            self.patch('wood', bx - 120 * s, by + 170 * s, 6, 70, 300)
        for cx, cy in ((1200, 800), (850, 520), (1550, 1080), (700, 1050), (1700, 560)):
            self.patch('wood', cx, cy, 7, 85, 300)
        for cx, cy in ((1200, 430), (1200, 1170), (1000, 800), (1400, 800)):
            self.patch('ore', cx, cy, 3, 50, 450)
        self.apply_setup()
        self.rebuild_obst()

    def apply_setup(self):
        S = self.setup
        for t, ku, kb in ((0, 'units', 'blds'), (1, 'e_units', 'e_blds')):
            bx, by = self.bases[t]
            s = 1 if t == 0 else -1
            for kind, n in S.get(ku, []):
                for i in range(n):
                    self.spawn(kind, t, bx + 90 * s + (i % 5) * 26, by + 120 * s + (i // 5) * 26)
            for kind, dx, dy in S.get(kb, []):
                for k in range(8):
                    x, y = bx + dx * s + k * 12, by + dy * s + k * 12
                    if self.free(x, y, self.bst[t][kind]['r'], 8):
                        self.add(self.make(kind, t, x, y, True))
                        break
        for team, what, kind, x, y in S.get('extra', []):
            if what == 'unit':
                self.spawn(kind, team, x, y)
            else:
                self.add(self.make(kind, team, x, y, True))
        self.init_bld = {}
        for e in self.ents:
            if e.b:
                self.init_bld[(e.team, e.kind)] = self.init_bld.get((e.team, e.kind), 0) + 1

    def norm_mission(self, m):
        if not m:
            return None
        m = dict(m)
        if 'objs' not in m and 'steps' not in m:
            m['objs'] = [dict(type=m['type'], target=m.get('target', 1), kind=m.get('kind'))]
        return m

    def note(self, name):
        self.flags.add(name)

    def ev(self, name, x=0, y=0):
        if len(self.events) < 40:
            self.events.append((name, x, y))

    def focus_base(self):
        return self.bases[self.me]

    def make(self, kind, team, x, y, building=False, done=True):
        d = (self.bst if building else self.ust)[team][kind]
        return Ent(kind, team, x, y, d, building, done)

    def add(self, e):
        e.id = self.nid
        self.nid += 1
        self.ents.append(e)
        self.by_id[e.id] = e
        return e

    def spawn(self, kind, team, x, y):
        return self.add(self.make(kind, team, x, y))

    def patch(self, kind, cx, cy, n, rad, amount):
        placed = 0
        for _ in range(300):
            if placed >= n:
                break
            a, d = self.rng.uniform(0, 6.283), self.rng.uniform(0, rad)
            x, y = cx + math.cos(a) * d, cy + math.sin(a) * d
            if self.free(x, y, 16, 2):
                r = Res(kind, x, y, amount, self.nid)
                self.nid += 1
                self.res.append(r)
                self.rid[r.id] = r
                placed += 1

    def rebuild_obst(self):
        self.obst = [(e.x, e.y, e.r) for e in self.ents if e.b and not e.dead]
        self.obst += [(r.x, r.y, r.r) for r in self.res] + list(self.rocks)
        blk = bytearray(GW * GH)
        for ox, oy, orr in self.obst:
            rad = orr + 22
            for cy in range(max(0, int((oy - rad) // CELL)), min(GH, int((oy + rad) // CELL) + 1)):
                for cx in range(max(0, int((ox - rad) // CELL)), min(GW, int((ox + rad) // CELL) + 1)):
                    if dist((cx + .5) * CELL, (cy + .5) * CELL, ox, oy) < rad:
                        blk[cx + cy * GW] = 1
        self.blk = blk
        self.fcache = {}

    # ------------------------------------------------------------ réseau : initialisation et instantanés
    def make_init(self, client_me=1):
        return dict(fac=[self.fac[0], self.fac[1]], me=client_me, rocks=[list(r) for r in self.rocks],
                    res=[[r.id, r.kind, round(r.x, 1), round(r.y, 1), r.amount] for r in self.res])

    def init_remote(self, p):
        self.reset(p['fac'][0], p['fac'][1], me=p['me'], ai_teams=(), remote=True)
        self.ents, self.by_id = [], {}
        self.rocks = [tuple(r) for r in p['rocks']]
        self.res, self.rid = [], {}
        for rid, kind, x, y, amount in p['res']:
            r = Res(kind, x, y, amount, rid)
            self.res.append(r)
            self.rid[rid] = r
        self.rebuild_obst()

    def snapshot(self):
        rows = []
        for e in self.ents:
            if e.dead:
                continue
            fl = (1 if e.moving else 0) | (2 if e.working else 0) | (4 if e.flash > 0 else 0) | (8 if e.built else 0)
            rows.append([e.id, e.kind, e.team, round(e.x, 1), round(e.y, 1), int(e.hp), round(e.ang, 2), fl, e.carry,
                         e.ctype or '', round(e.bt, 1), e.queue, round(e.qt, 1),
                         [round(e.rally[0]), round(e.rally[1])] if e.rally else None, 1 if e.b else 0])
        s = dict(t=round(self.time, 1), e=rows, r=[[r.id, r.amount] for r in self.res],
                 s=[[self.stock[t]['wood'], self.stock[t]['ore']] for t in (0, 1)], fx=self.fx_out[:40],
                 w=self.winner, why=self.reason, g=[self.gathered[0], self.gathered[1]])
        self.fx_out = []
        return s

    def apply_snapshot(self, s):
        self.time = s['t']
        seen = set()
        for (id_, kind, team, x, y, hp, ang, fl, carry, ctype, bt, queue, qt, rally, isb) in s['e']:
            e = self.by_id.get(id_)
            if e is None:
                e = self.make(kind, team, x, y, bool(isb), True)
                e.id = id_
                self.ents.append(e)
                self.by_id[id_] = e
                if isb:
                    self.rebuild_obst()
            e.tx, e.ty = x, y
            e.hp, e.ang = hp, ang
            e.moving, e.working = bool(fl & 1), bool(fl & 2)
            e.flash = 0.15 if fl & 4 else 0.0
            e.built = bool(fl & 8)
            e.carry, e.ctype, e.bt = carry, (ctype or None), bt
            e.queue, e.qt = list(queue), qt
            e.rally = tuple(rally) if rally else None
            seen.add(id_)
        gone = [e for e in self.ents if e.id not in seen]
        for e in gone:
            e.dead = True
            self.puff(e.x, e.y, (0.85, 0.85, 0.85) if e.b else (0.9, 0.3, 0.3), 14 if e.b else 6, 80, 0.6, 4)
        if gone:
            self.ents = [e for e in self.ents if not e.dead]
            self.by_id = {e.id: e for e in self.ents}
            self.sel = [e for e in self.sel if not e.dead]
            if any(e.b for e in gone):
                self.rebuild_obst()
        amounts = dict(s['r'])
        n = len(self.res)
        for r in self.res:
            r.amount = amounts.get(r.id, 0)
        self.res = [r for r in self.res if r.amount > 0]
        if len(self.res) != n:
            self.rebuild_obst()
        for t in (0, 1):
            self.stock[t]['wood'], self.stock[t]['ore'] = s['s'][t]
        self.gathered = {0: s['g'][0], 1: s['g'][1]}
        for f in s['fx']:
            if f[0] == 'p':
                self.puff(f[1], f[2], tuple(f[3]), f[4], f[5], f[6], f[7], record=False)
            else:
                self.fx.append(dict(t='a', x=f[1], y=f[2], x1=f[3], y1=f[4], life=0.22, max=0.22))
        if s['w'] is not None and self.winner is None:
            self.set_winner(s['w'], s['why'])

    def update_remote(self, dt):
        self.time += dt
        self.msg_t = max(0, self.msg_t - dt)
        k = min(1.0, dt * 12)
        for e in self.ents:
            e.x += (e.tx - e.x) * k
            e.y += (e.ty - e.y) * k
        self.age_fx(dt)

    # ------------------------------------------------------------ utilitaires
    def say(self, text):
        self.msg, self.msg_t = text, 2.5

    def free(self, x, y, r, pad=6):
        if x < r or y < r or x > MAP_W - r or y > MAP_H - r:
            return False
        for o in self.ents:
            if o.b and not o.dead and dist(o.x, o.y, x, y) < o.r + r + pad:
                return False
        for o in self.res:
            if dist(o.x, o.y, x, y) < o.r + r + pad:
                return False
        for ox, oy, orr in self.rocks:
            if dist(ox, oy, x, y) < orr + r + pad:
                return False
        return True

    def pop(self, team):
        return sum(1 for e in self.ents if e.team == team and not e.b and not e.dead)

    def mil(self, team):
        return [e for e in self.ents if e.team == team and not e.b and e.kind != 'worker' and not e.dead]

    def nearest_enemy(self, u, rad, units_only=False):
        best, bd = None, rad
        for e in self.ents:
            if e.team != u.team and not e.dead and not (units_only and e.b):
                d = dist(u.x, u.y, e.x, e.y) - e.r
                if d < bd:
                    best, bd = e, d
        return best

    def nearest_res(self, x, y, kind):
        best, bd = None, 1e9
        for r in self.res:
            if r.kind == kind and r.amount > 0:
                d = dist(x, y, r.x, r.y)
                if d < bd:
                    best, bd = r, d
        return best

    def nearest_drop(self, u):
        best, bd = None, 1e9
        for e in self.ents:
            if e.team == u.team and e.b and e.built and e.kind in ('hq', 'depot') and not e.dead:
                d = dist(u.x, u.y, e.x, e.y)
                if d < bd:
                    best, bd = e, d
        return best

    def puff(self, x, y, col, n=6, speed=60, life=0.5, size=3, record=True):
        if self.record_fx and record and len(self.fx_out) < 60:
            self.fx_out.append(['p', round(x), round(y), list(col), n, speed, life, size])
        for _ in range(n):
            a, s = random.uniform(0, 6.283), random.uniform(0.3, 1) * speed
            self.fx.append(dict(t='p', x=x, y=y, vx=math.cos(a) * s, vy=math.sin(a) * s,
                                life=life, max=life, col=col, size=size))
        if len(self.fx) > 250:
            del self.fx[:60]

    def age_fx(self, dt):
        for f in self.fx:
            f['life'] -= dt
            if f['t'] == 'p':
                f['x'] += f['vx'] * dt
                f['y'] += f['vy'] * dt
        self.fx = [f for f in self.fx if f['life'] > 0]
        for c in self.corpses:
            c[5] -= dt
        self.corpses = [c for c in self.corpses if c[5] > 0]

    # ------------------------------------------------------------ actions
    def affordable(self, team, cost):
        st = self.stock[team]
        return st['wood'] >= cost[0] and st['ore'] >= cost[1]

    def queue(self, b, kind):
        if not b.built or kind not in b.d['makes'] or len(b.queue) >= 5:
            return False
        c = self.ust[b.team][kind]['cost']
        if not self.affordable(b.team, c):
            return False
        st = self.stock[b.team]
        st['wood'] -= c[0]
        st['ore'] -= c[1]
        b.queue.append(kind)
        return True

    def cancel(self, b):
        if b.queue:
            c = self.ust[b.team][b.queue.pop()]['cost']
            st = self.stock[b.team]
            st['wood'] += c[0]
            st['ore'] += c[1]
            if not b.queue:
                b.qt = 0.0
        elif b.research:
            c = TECHS[b.research]['cost']
            st = self.stock[b.team]
            st['wood'] += c[0]
            st['ore'] += c[1]
            b.research, b.rt = None, 0.0

    def req_ok(self, team, kind):
        return all(any(e.b and e.team == team and e.built and e.kind == r and not e.dead for e in self.ents)
                   for r in self.bst[team][kind].get('req', []))

    def can_place(self, team, kind, x, y):
        if not self.free(x, y, self.bst[team][kind]['r'], 8):
            return False
        return any(e.b and e.built and e.team == team and not e.dead and dist(e.x, e.y, x, y) < 450
                   for e in self.ents)

    def place(self, team, kind, x, y):
        c = self.bst[team][kind]['cost']
        if not self.affordable(team, c) or not self.req_ok(team, kind) or not self.can_place(team, kind, x, y):
            return None
        st = self.stock[team]
        st['wood'] -= c[0]
        st['ore'] -= c[1]
        b = self.add(self.make(kind, team, x, y, True, False))
        self.rebuild_obst()
        return b

    def order_move(self, u, x, y):
        u.mode, u.dest, u.target, u.auto, u.resume, u.lr, u.st = 'move', (x, y), None, False, None, 1e9, 0.0

    def order_amove(self, u, x, y):
        u.mode, u.dest, u.target, u.auto, u.resume, u.lr, u.st = 'amove', (x, y), None, False, None, 1e9, 0.0

    def order_harvest(self, u, r):
        if u.carry and u.ctype != r.kind:
            u.carry = 0
        u.mode, u.target, u.ctype, u.hs, u.auto, u.resume = 'harvest', r, r.kind, 'go', False, None

    def order_attack(self, u, t, auto=False):
        u.mode, u.target, u.auto, u.home, u.resume = 'attack', t, auto, (u.x, u.y), None

    def order_build(self, u, b):
        if u.mode == 'harvest' and isinstance(u.target, Res):
            u.prev = u.target
        u.mode, u.target, u.auto, u.resume = 'build', b, False, None

    def stop(self, u):
        u.mode, u.target, u.resume, u.prev = 'idle', None, None, None

    # ---- recherches
    def research(self, b, tid):
        t = TECHS.get(tid)
        if not t or not b.built or b.research or b.kind != t['bld'] or b.dead:
            return False
        team = b.team
        if tid in self.techs[team] or any(e.research == tid for e in self.ents if e.team == team):
            return False
        if any(r not in self.techs[team] for r in t['req']):
            return False
        if not self.affordable(team, t['cost']):
            return False
        st = self.stock[team]
        st['wood'] -= t['cost'][0]
        st['ore'] -= t['cost'][1]
        b.research, b.rt = tid, 0.0
        return True

    def finish_research(self, b):
        tid = b.research
        b.research, b.rt = None, 0.0
        self.apply_tech(b.team, tid)
        if b.team == self.me:
            self.ev('tech', b.x, b.y)
        self.puff(b.x, b.y - 30, (1, .95, .6), 12, 70, .8, 4)

    def apply_tech(self, team, tid):
        if tid in self.techs[team]:
            return
        self.techs[team].add(tid)
        fx = TECH_FX.get(self.fac[team], {}).get(tid, TECHS[tid]['fx'])
        for scope, kinds, stat, op, v in fx:
            if scope == 'u':
                for k in kinds:
                    d = self.ust[team][k]
                    if stat == 'hp' and op == 'mul':
                        d['hp'] = int(d['hp'] * v)
                        for e in self.ents:
                            if e.team == team and e.kind == k and not e.b and not e.dead:
                                e.maxhp = d['hp']
                                e.hp = min(e.maxhp, e.hp * v)
                    elif op == 'add':
                        d[stat] += v
                    else:
                        d[stat] *= v
            elif scope == 'b':
                for k, d in self.bst[team].items():
                    d['hp'] = int(d['hp'] * v)
                for e in self.ents:
                    if e.team == team and e.b and not e.dead:
                        e.maxhp = self.bst[team][e.kind]['hp']
                        e.hp = min(e.maxhp, e.hp * v)
            elif scope == 'g':
                self.gmult[team] += v
            elif scope == 'a':
                self.abmul[team] *= v
            elif scope == 'h':
                self.healmul[team] *= v

    def use_ability(self, team):
        if self.abcd[team] > 0 or self.winner is not None:
            return False
        fac = self.fac[team]
        ab = FACTIONS[fac]['ability']
        self.abcd[team] = ab['cd'] * self.abmul[team]
        self.buff[team] = ab['dur']
        col = {'kingdom': (1, .85, .35), 'horde': (1, .35, .2), 'sylvan': (.45, 1, .65)}[fac]
        n = 0
        for e in self.ents:
            if e.team == team and not e.b and not e.dead:
                if fac == 'sylvan':
                    e.hp = min(e.maxhp, e.hp + .45 * e.maxhp)
                if e.kind != 'worker' and n < 26:
                    self.puff(e.x, e.y - 8, col, 3, 60, .7, 3)
                    n += 1
        hq = next((e for e in self.ents if e.team == team and e.kind == 'hq'), None)
        if hq:
            self.fx.append(dict(t='w', x=hq.x, y=hq.y, life=1.1, max=1.1, col=col))
            if self.record_fx and len(self.fx_out) < 60:
                self.fx_out.append(['w', round(hq.x), round(hq.y), list(col)])
        if team == self.me:
            self.ev('power')
        return True

    def spdmul(self, team):
        if self.buff[team] > 0:
            f = self.fac[team]
            return 1.15 if f == 'kingdom' else (1.2 if f == 'horde' else 1.0)
        return 1.0

    def heal_pulse(self, u, dt):
        u.hl -= dt
        tgt, best = None, .999
        for e in self.ents:
            if e.team == u.team and not e.b and e is not u and not e.dead and e.hp < e.maxhp and dist(u.x, u.y, e.x, e.y) <= 140:
                r = e.hp / e.maxhp
                if r < best:
                    best, tgt = r, e
        if tgt:
            tgt.hp = min(tgt.maxhp, tgt.hp + u.d['heal'] * self.healmul[u.team] * dt)
            if u.hl <= 0:
                u.hl = .7
                u.flash = .15
                col = {'kingdom': (1, .95, .55), 'horde': (.5, 1, .45), 'sylvan': (.55, 1, .9)}[self.fac[u.team]]
                self.puff(tgt.x, tgt.y - 10, col, 4, 40, .6, 3)
                self.ev('heal', u.x, u.y)
        return tgt

    # ---- commandes (exécutées localement, ou envoyées à l'hôte en mode réseau)
    def cmd(self, c):
        k = c.get('k')
        if k == 'place':
            self.note('place_' + c['kind'])
        elif k == 'prod':
            self.note('prod_' + c['kind'])
        elif k == 'research':
            self.note('research')
            self.note('research_' + c['tech'])
        elif k == 'ability':
            self.note('ability')
        elif k == 'rally':
            self.note('rally')
        elif k == 'orders':
            codes = {o[1] for o in c['o']}
            for code, name in (('m', 'move'), ('am', 'amove'), ('at', 'attack'), ('h', 'harvest'), ('s', 'stop')):
                if code in codes:
                    self.note(name)
        if self.remote:
            self.outbox.append(c)
        else:
            self.exec_cmd(self.me, c)

    def exec_cmd(self, team, c):
        k = c.get('k')
        if k == 'orders':
            for id_, code, a, b in c['o']:
                u = self.by_id.get(id_)
                if not u or u.dead or u.team != team or u.b:
                    continue
                if code == 'm':
                    self.order_move(u, a, b)
                elif code == 'am':
                    self.order_amove(u, a, b)
                elif code == 'at':
                    t = self.by_id.get(a)
                    if t and not t.dead and t.team != team:
                        self.order_attack(u, t)
                elif code == 'h':
                    r = self.rid.get(a)
                    if r and r.amount > 0 and u.kind == 'worker':
                        self.order_harvest(u, r)
                elif code == 'b':
                    bb = self.by_id.get(a)
                    if bb and not bb.dead and bb.team == team and u.kind == 'worker':
                        self.order_build(u, bb)
                elif code == 's':
                    self.stop(u)
        elif k == 'place':
            if c['kind'] not in self.bst[team] or c['kind'] == 'hq':
                return
            b = self.place(team, c['kind'], c['x'], c['y'])
            if b:
                ws = [self.by_id.get(i) for i in c.get('ids', [])]
                ws = [w for w in ws if w and w.team == team and w.kind == 'worker' and not w.dead]
                if not ws:
                    ws = sorted([e for e in self.ents if e.team == team and e.kind == 'worker'],
                                key=lambda e: dist(e.x, e.y, b.x, b.y))[:1]
                for w in ws:
                    self.order_build(w, b)
        elif k == 'prod':
            b = self.by_id.get(c['id'])
            if b and b.team == team and b.b:
                self.queue(b, c['kind'])
        elif k == 'cancel':
            b = self.by_id.get(c['id'])
            if b and b.team == team and b.b:
                self.cancel(b)
        elif k == 'rally':
            b = self.by_id.get(c['id'])
            if b and b.team == team and b.b and b.d['makes']:
                b.rally = (c['x'], c['y'])
        elif k == 'research':
            b = self.by_id.get(c['id'])
            if b and b.team == team and b.b:
                self.research(b, c['tech'])
        elif k == 'ability':
            self.use_ability(team)

    # ---- interface joueur
    def start_place(self, kind):
        if not self.affordable(self.me, self.bst[self.me][kind]['cost']):
            self.say('Ressources insuffisantes')
        else:
            self.placing = kind

    def build_with_selected(self, kind, x, y):
        if not self.can_place(self.me, kind, x, y) or not self.affordable(self.me, self.bst[self.me][kind]['cost']):
            return False
        ids = [e.id for e in self.sel if e.team == self.me and e.kind == 'worker']
        self.cmd(dict(k='place', kind=kind, x=round(x, 1), y=round(y, 1), ids=ids))
        return True

    def produce(self, kind):
        cands = [e for e in self.sel if e.team == self.me and e.b and e.built and kind in e.d['makes']]
        if not cands:
            return
        b = min(cands, key=lambda e: len(e.queue))
        if not self.affordable(self.me, self.ust[self.me][kind]['cost']) or len(b.queue) >= 5:
            self.say('Ressources insuffisantes ou file pleine')
            return
        self.cmd(dict(k='prod', id=b.id, kind=kind))

    def cancel_selected(self):
        for e in self.sel:
            if e.team == self.me and e.b and e.queue:
                self.cmd(dict(k='cancel', id=e.id))
                break

    def actions(self):
        me = self.me
        own = [e for e in self.sel if e.team == me]
        out = []
        if any(e.kind == 'worker' for e in own):
            for k in ('barracks', 'stable', 'depot', 'tower'):
                out.append(dict(kind=k, d=self.bst[me][k], fn=lambda k=k: self.start_place(k)))
        kinds = []
        for e in own:
            if e.b and e.built:
                kinds += [k for k in e.d['makes'] if k not in kinds]
        for k in kinds:
            out.append(dict(kind=k, d=self.ust[me][k], fn=lambda k=k: self.produce(k)))
        if any(e.b and e.queue for e in own):
            out.append(dict(kind='cancel', d=dict(label='Annuler', cost=(0, 0)), fn=self.cancel_selected))
        for a in out:
            a['ok'] = self.affordable(me, a['d']['cost'])
        return out

    def pick(self, wx, wy):
        def dd(e):
            d = dist(e.x, e.y, wx, wy)
            return d if e.b else min(d, dist(e.x, e.y - e.r * 1.5, wx, wy))
        c = [e for e in self.ents if dd(e) <= e.r + 8]
        c.sort(key=lambda e: (e.b, dd(e)))
        return c[0] if c else None

    def select_rect(self, x0, y0, x1, y1):
        xa, xb, ya, yb = min(x0, x1), max(x0, x1), min(y0, y1), max(y0, y1)
        self.sel = [e for e in self.ents if e.team == self.me and not e.b and xa <= e.x <= xb and ya <= e.y <= yb]

    def select_kind(self, kind, x0, y0, x1, y1):
        self.sel = [e for e in self.ents if e.team == self.me and not e.b and e.kind == kind
                    and x0 <= e.x <= x1 and y0 <= e.y <= y1]

    def select_army(self):
        self.sel = self.mil(self.me)

    def select_idle_workers(self):
        self.sel = [e for e in self.ents if e.team == self.me and e.kind == 'worker' and (e.mode == 'idle' or self.remote and not e.moving and not e.working and not e.carry)]
        if not self.sel:
            self.say('Aucun récolteur inactif')

    def stop_selected(self):
        o = [[e.id, 's', 0, 0] for e in self.sel if e.team == self.me and not e.b]
        if o:
            self.cmd(dict(k='orders', o=o))

    def command(self, wx, wy):
        me = self.me
        own = [e for e in self.sel if e.team == me]
        us = [e for e in own if not e.b]
        if not us:
            for b in own:
                if b.d['makes']:
                    self.cmd(dict(k='rally', id=b.id, x=round(wx), y=round(wy)))
                    self.say('Point de ralliement défini')
            return
        tgt = next((e for e in self.ents if e.team != me and dist(e.x, e.y, wx, wy) <= e.r + 8), None)
        if tgt:
            self.amove = False
            self.cmd(dict(k='orders', o=[[u.id, 'at', tgt.id, 0] for u in us]))
            return
        r = next((r for r in self.res if dist(r.x, r.y, wx, wy) <= r.r + 8), None)
        if r and not self.amove:
            o = [[u.id, 'h', r.id, 0] if u.kind == 'worker' else [u.id, 'm', round(r.x), round(r.y + 30)] for u in us]
            self.cmd(dict(k='orders', o=o))
            return
        code = 'am' if self.amove else 'm'
        self.amove = False
        n = len(us)
        cols = math.ceil(math.sqrt(n))
        rows = math.ceil(n / cols)
        o = []
        for i, u in enumerate(us):
            ox = (i % cols - (cols - 1) / 2) * 28
            oy = (i // cols - (rows - 1) / 2) * 28
            o.append([u.id, code, round(wx + ox), round(wy + oy)])
        self.cmd(dict(k='orders', o=o))

    # ------------------------------------------------------------ combat
    def strike(self, a, t):
        d = a.d
        mult = BONUS.get((a.kind, t.kind), 1.0)
        if t.b:
            mult *= BUILD_MULT.get(a.kind, 1.0)
        dmg = max(1.0, d['dmg'] * mult - (0 if t.b else t.d.get('armor', 0)))
        t.hp -= dmg
        a.cd, a.flash = d['cd'], 0.15
        a.ang = math.atan2(t.y - a.y, t.x - a.x)
        if d['rng'] > 60:
            self.fx.append(dict(t='a', x=a.x, y=a.y, x1=t.x, y1=t.y, life=0.22, max=0.22))
            if self.record_fx and len(self.fx_out) < 60:
                self.fx_out.append(['a', round(a.x), round(a.y), round(t.x), round(t.y)])
        else:
            self.puff(t.x, t.y, (1, 0.9, 0.5), 3, 40, 0.25, 2)
        if t.hp <= 0 and not t.dead:
            t.dead = True
            self.puff(t.x, t.y, (0.8, 0.8, 0.8) if t.b else (0.9, 0.3, 0.3), 16 if t.b else 8, 90, 0.7, 4)
            if t.b:
                self.rebuild_obst()

    # ------------------------------------------------------------ déplacement
    def field(self, gx, gy):
        key = (gx, gy)
        f = self.fcache.get(key)
        if f is not None:
            return f
        if len(self.fcache) > 60:
            self.fcache.clear()
        INF = 1e9
        blk = self.blk
        f = [INF] * (GW * GH)
        g = gx + gy * GW
        f[g] = 0.0
        h = [(0.0, g)]
        while h:
            d, i = heapq.heappop(h)
            if d > f[i]:
                continue
            x, y = i % GW, i // GW
            for dx, dy, c in NB:
                nx, ny = x + dx, y + dy
                if nx < 0 or ny < 0 or nx >= GW or ny >= GH:
                    continue
                j = nx + ny * GW
                if blk[j] and (nx - gx) ** 2 + (ny - gy) ** 2 > 4:
                    continue
                if dx and dy and (blk[nx + y * GW] or blk[x + ny * GW]):
                    continue
                nd = d + c
                if nd < f[j]:
                    f[j] = nd
                    heapq.heappush(h, (nd, j))
        self.fcache[key] = f
        return f

    def clear(self, x0, y0, x1, y1):
        d = dist(x0, y0, x1, y1)
        n = max(1, int(d // 20))
        for k in range(n + 1):
            t = k / n
            cx, cy = int((x0 + (x1 - x0) * t) // CELL), int((y0 + (y1 - y0) * t) // CELL)
            if 0 <= cx < GW and 0 <= cy < GH and self.blk[cx + cy * GW]:
                return False
        return True

    def flow_dir(self, u, tx, ty):
        gx, gy = min(GW - 1, max(0, int(tx // CELL))), min(GH - 1, max(0, int(ty // CELL)))
        f = self.field(gx, gy)
        cx, cy = min(GW - 1, max(0, int(u.x // CELL))), min(GH - 1, max(0, int(u.y // CELL)))
        aim = None
        for _ in range(3):
            bd, best = f[cx + cy * GW], None
            for dx, dy, c in NB:
                nx, ny = cx + dx, cy + dy
                if 0 <= nx < GW and 0 <= ny < GH and f[nx + ny * GW] < bd - 1e-6:
                    bd, best = f[nx + ny * GW], (nx, ny)
            if best is None:
                break
            px, py = (best[0] + .5) * CELL, (best[1] + .5) * CELL
            if aim is not None and not self.clear(u.x, u.y, px, py):
                break
            aim = (px, py)
            cx, cy = best
        if aim is None:
            return None
        d = dist(u.x, u.y, aim[0], aim[1])
        if d < 1:
            return None
        return (aim[0] - u.x) / d, (aim[1] - u.y) / d

    def avoid(self, u, dx, dy, tx, ty):
        best_t, best = 1e9, None
        for ox, oy, orr in self.obst:
            if abs(ox - tx) < 1 and abs(oy - ty) < 1:
                continue
            rx, ry = ox - u.x, oy - u.y
            t = rx * dx + ry * dy
            rr = orr + u.r + 6
            if t <= 0 or t > 50 + rr or t >= best_t:
                continue
            pd = math.hypot(rx - dx * t, ry - dy * t)
            if pd < rr:
                best_t, best = t, (rx, ry, (rr - pd) / rr)
        if best:
            rx, ry, k = best
            side = 1 if dx * ry - dy * rx > 0 else -1
            a = -side * (0.8 + 0.7 * k)
            c, s = math.cos(a), math.sin(a)
            return dx * c - dy * s, dx * s + dy * c
        return dx, dy

    def step(self, u, tx, ty, dt, stop=0):
        d = dist(u.x, u.y, tx, ty)
        if d - stop <= 0.5:
            u.moving = False
            return 0
        dx, dy = (tx - u.x) / d, (ty - u.y) / d
        L = min(d, 200)
        if not self.clear(u.x, u.y, u.x + dx * L, u.y + dy * L):
            v = self.flow_dir(u, tx, ty)
            if v:
                dx, dy = v
        dx, dy = self.avoid(u, dx, dy, tx, ty)
        m = min(u.d['speed'] * dt, d - stop)
        u.x += dx * m
        u.y += dy * m
        u.ang = math.atan2(dy, dx)
        u.moving = True
        return max(0, dist(u.x, u.y, tx, ty) - stop)

    def acquire_range(self, u):
        return max(190, u.d['rng'] + 50)

    def after_attack(self, u):
        u.target = None
        if u.resume:
            u.mode, u.dest, u.resume, u.lr, u.st = 'amove', u.resume, None, 1e9, 0.0
        else:
            u.mode = 'idle'

    def upd_unit(self, u, dt):
        u.cd = max(0, u.cd - dt)
        u.flash = max(0, u.flash - dt)
        u.moving = u.working = False
        if u.mode == 'idle' and u.kind != 'worker':
            t = self.nearest_enemy(u, self.acquire_range(u))
            if t:
                self.order_attack(u, t, auto=True)
        if u.mode == 'move':
            self.go(u, dt)
        elif u.mode == 'amove':
            t = self.nearest_enemy(u, self.acquire_range(u)) if u.kind != 'worker' else None
            if t:
                keep = u.dest
                self.order_attack(u, t, auto=True)
                u.resume = keep
            else:
                self.go(u, dt)
        elif u.mode == 'attack':
            t = u.target
            if t is None or t.dead:
                self.after_attack(u)
                return
            if t.b:
                n = self.nearest_enemy(u, u.d['rng'] + 70, units_only=True)
                if n:
                    u.target = t = n
            if u.auto and dist(u.x, u.y, u.home[0], u.home[1]) > 320:
                self.after_attack(u)
                return
            d = dist(u.x, u.y, t.x, t.y) - t.r - u.r
            if d <= u.d['rng']:
                u.ang = math.atan2(t.y - u.y, t.x - u.x)
                if u.cd <= 0:
                    self.strike(u, t)
            else:
                self.step(u, t.x, t.y, dt, stop=t.r + u.r + u.d['rng'] * 0.85)
        elif u.mode == 'harvest':
            self.harvest(u, dt)
        elif u.mode == 'build':
            self.construct(u, dt)

    def go(self, u, dt):
        rem = self.step(u, u.dest[0], u.dest[1], dt)
        u.st += dt
        if u.st >= 1.0:
            if u.lr - rem < 8:
                rem = 0
            u.lr, u.st = rem, 0.0
        if rem <= 2:
            u.mode = 'idle'

    def construct(self, u, dt):
        b = u.target
        if b is None or b.dead or b.built:
            u.mode, u.target = 'idle', None
            if u.prev and u.prev.amount > 0:
                self.order_harvest(u, u.prev)
            u.prev = None
            return
        if self.step(u, b.x, b.y, dt, stop=b.r + u.r + 3) <= 1:
            u.working = True
            u.ang = math.atan2(b.y - u.y, b.x - u.x)
            b.bt += dt
            b.hp = min(b.maxhp, b.hp + b.maxhp * 0.8 / b.d['time'] * dt)
            if b.bt >= b.d['time']:
                b.built, b.hp = True, b.maxhp
                self.puff(b.x, b.y, (1, 0.9, 0.6), 14, 80, 0.7, 4)

    def harvest(self, u, dt):
        r = u.target
        if u.hs != 'return' and (r is None or r.amount <= 0):
            r = u.target = self.nearest_res(u.x, u.y, u.ctype or 'wood')
            if r is None:
                if u.carry > 0:
                    u.hs = 'return'
                else:
                    u.mode = 'idle'
                    return
        if u.hs == 'go':
            if self.step(u, r.x, r.y, dt, stop=r.r + u.r + 2) <= 1:
                u.hs, u.gt = 'gather', 0.0
        elif u.hs == 'gather':
            u.working = True
            u.ang = math.atan2(r.y - u.y, r.x - u.x)
            u.gt += dt
            if u.gt >= 1.0:
                u.gt = 0.0
                take = min(5, r.amount, 10 - u.carry)
                r.amount -= take
                u.carry += take
                if u.carry >= 10 or r.amount <= 0:
                    u.hs = 'return'
        elif u.hs == 'return':
            b = self.nearest_drop(u)
            if b is None:
                u.mode = 'idle'
                return
            if self.step(u, b.x, b.y, dt, stop=b.r + u.r + 2) <= 1:
                k = FACTIONS[self.fac[u.team]]['gather'] * (AI_GATHER[self.diff] if u.team in self.ai_teams else 1.0)
                got = int(round(u.carry * k))
                self.stock[u.team][u.ctype] += got
                self.gathered[u.team] += got
                u.carry, u.hs = 0, 'go'

    def upd_building(self, b, dt):
        if not b.built:
            return
        b.flash = max(0, b.flash - dt)
        if b.kind == 'tower':
            b.cd = max(0, b.cd - dt)
            if b.cd <= 0:
                t = self.nearest_enemy(b, b.d['rng'], units_only=True)
                if t:
                    self.strike(b, t)
        if b.queue:
            k = b.queue[0]
            tm = self.ust[b.team][k]['time']
            b.qt += dt
            if b.qt >= tm:
                if self.pop(b.team) < POP_MAX:
                    b.queue.pop(0)
                    b.qt = 0.0
                    u = self.spawn(k, b.team, b.x + random.uniform(-25, 25), b.y + b.r + 20)
                    if b.rally:
                        self.order_move(u, *b.rally)
                else:
                    b.qt = tm

    def separate(self):
        us = [e for e in self.ents if not e.b and not e.dead]
        for i, a in enumerate(us):
            for c in us[i + 1:]:
                dx, dy = c.x - a.x, c.y - a.y
                if abs(dx) > 34 or abs(dy) > 34:
                    continue
                d = math.hypot(dx, dy)
                m = a.r + c.r
                if 0 < d < m:
                    p = (m - d) / 2
                    dx, dy = dx / d * p, dy / d * p
                    a.x -= dx
                    a.y -= dy
                    c.x += dx
                    c.y += dy
                elif d == 0:
                    a.x += 0.5
            for ox, oy, orr in self.obst:
                dx, dy = a.x - ox, a.y - oy
                if abs(dx) > orr + 34 or abs(dy) > orr + 34:
                    continue
                d = math.hypot(dx, dy)
                m = a.r + orr
                if 0 < d < m - 1:
                    a.x += dx / d * (m - d)
                    a.y += dy / d * (m - d)
            a.x = max(a.r, min(MAP_W - a.r, a.x))
            a.y = max(a.r, min(MAP_H - a.r, a.y))

    def update(self, dt):
        if self.remote:
            self.update_remote(dt)
            return
        self.time += dt
        self.msg_t = max(0, self.msg_t - dt)
        for e in self.ents:
            if not e.dead:
                (self.upd_building if e.b else self.upd_unit)(e, dt)
        self.separate()
        n = len(self.res)
        self.ents = [e for e in self.ents if not e.dead]
        self.by_id = {e.id: e for e in self.ents}
        self.res = [r for r in self.res if r.amount > 0]
        if len(self.res) != n:
            self.rid = {r.id: r for r in self.res}
            self.rebuild_obst()
        self.sel = [e for e in self.sel if not e.dead]
        self.age_fx(dt)
        for t in self.ai_teams:
            self.ai(t, dt)
        self.check_end()

    # ------------------------------------------------------------ fin de partie / objectifs
    def set_winner(self, w, why=''):
        self.winner, self.reason = w, why
        self.over = ('VICTOIRE !' if w == self.me else 'DÉFAITE...')

    def check_end(self):
        if self.winner is not None:
            return
        hq = {t: any(e.kind == 'hq' and e.team == t for e in self.ents) for t in (0, 1)}
        me, foe = self.me, 1 - self.me
        if not hq[me]:
            self.set_winner(foe, 'Votre base est détruite.')
            return
        if not hq[foe]:
            self.set_winner(me, "La base ennemie est détruite.")
            return
        m = self.mission
        if not m:
            return
        ty = m['type']
        if ty == 'survive' and self.time >= m['target']:
            self.set_winner(me, 'Vous avez tenu bon !')
        elif ty == 'army' and self.army_count() >= m['target']:
            self.set_winner(me, 'Votre armée est prête.')
        elif ty == 'gather' and self.gathered[me] >= m['target']:
            self.set_winner(me, 'Les réserves sont pleines.')

    def army_count(self):
        m = self.mission or {}
        us = self.mil(self.me)
        if m.get('kind'):
            us = [u for u in us if u.kind == m['kind']]
        return len(us)

    def objective_text(self):
        m = self.mission
        if not m:
            return ''
        ty = m['type']
        if ty == 'destroy_hq':
            return 'Objectif : détruire la base ennemie'
        if ty == 'survive':
            left = max(0, int(m['target'] - self.time))
            return 'Objectif : survivre encore %d:%02d' % (left // 60, left % 60)
        if ty == 'army':
            nm = (self.ust[self.me][m['kind']]['label'].lower() + 's') if m.get('kind') else 'unités militaires'
            return 'Objectif : %d %s (%d/%d)' % (m['target'], nm, self.army_count(), m['target'])
        if ty == 'gather':
            return 'Objectif : récolter %d (%d/%d)' % (m['target'], min(m['target'], self.gathered[self.me]), m['target'])
        return ''

    # ------------------------------------------------------------ IA
    @staticmethod
    def power(units):
        return sum(u.hp * u.d['dmg'] for u in units)

    def ai(self, T, dt):
        S = self.aist[T]
        S['t'] += dt
        if S['t'] < S['think']:
            return
        S['t'] = 0.0
        F = 1 - T
        st = self.stock[T]
        mine = [e for e in self.ents if e.team == T]
        hq = next((e for e in mine if e.kind == 'hq'), None)
        if not hq:
            return
        foes = [e for e in self.ents if e.team == F]
        workers = [e for e in mine if e.kind == 'worker']
        army = [e for e in mine if not e.b and e.kind != 'worker']
        blds = [e for e in mine if e.b]
        bars = [e for e in blds if e.kind == 'barracks']
        stables = [e for e in blds if e.kind == 'stable']
        cnt = lambda k: sum(1 for e in blds if e.kind == k)

        target_w = 6 if not bars else (8 if len(army) < 8 else 10)
        if len(workers) < target_w and not hq.queue:
            self.queue(hq, 'worker')
        wood_w = [w for w in workers if w.mode == 'harvest' and w.ctype == 'wood']
        ore_w = [w for w in workers if w.mode == 'harvest' and w.ctype == 'ore']
        for w in workers:
            if w.mode == 'idle':
                kind = 'wood' if len(wood_w) <= 1.5 * len(ore_w) else 'ore'
                other = 'ore' if kind == 'wood' else 'wood'
                r = self.nearest_res(hq.x, hq.y, kind) or self.nearest_res(hq.x, hq.y, other)
                if r:
                    self.order_harvest(w, r)
                    (wood_w if r.kind == 'wood' else ore_w).append(w)
        if st['wood'] > st['ore'] + 150 and len(wood_w) > 1:
            r = self.nearest_res(hq.x, hq.y, 'ore')
            if r:
                self.order_harvest(wood_w[0], r)
        elif st['ore'] > st['wood'] + 150 and len(ore_w) > 1:
            r = self.nearest_res(hq.x, hq.y, 'wood')
            if r:
                self.order_harvest(ore_w[0], r)

        if workers and all(b.built for b in blds):
            n = len(army)
            want = None
            if not bars:
                want = 'barracks'
            elif not stables and n >= 3:
                want = 'stable'
            elif cnt('tower') < 2 and n >= 5:
                want = 'tower'
            elif cnt('barracks') < 2 and n >= 8:
                want = 'barracks'
            elif len(stables) < 2 and n >= 12:
                want = 'stable'
            elif cnt('tower') < 4 and n >= 14:
                want = 'tower'
            elif cnt('depot') == 0 and st['wood'] >= 250:
                want = 'depot'
            if want:
                self.ai_build(T, hq, want, workers)

        pk = [e.kind for e in foes if not e.b and e.kind != 'worker']
        cs, ca, ck = pk.count('soldier'), pk.count('archer'), pk.count('knight')
        if ck > 0 and ck >= max(ca, cs):
            counter = 'soldier'
        elif ca > 0 and ca >= cs:
            counter = 'knight'
        elif cs > 0:
            counter = 'archer'
        else:
            counter = random.choice(['soldier', 'archer', 'knight'])
        for b in bars + stables:
            if b.built and len(b.queue) < 2:
                opts = b.d['makes']
                k = counter if counter in opts and random.random() < 0.65 else random.choice(opts)
                self.queue(b, k)

        threats = [e for e in foes if not e.b and any(dist(e.x, e.y, b.x, b.y) < 330 for b in blds)]
        if threats:
            for a in army:
                if dist(a.x, a.y, hq.x, hq.y) < 700 and (a.mode in ('idle', 'move', 'amove') or
                                                         (a.mode == 'attack' and a.target and a.target.b)):
                    t = min(threats, key=lambda e: dist(a.x, a.y, e.x, e.y))
                    self.order_attack(a, t)
            return

        rally = (hq.x + (self.bases[F][0] - hq.x) * 0.06, hq.y + (self.bases[F][1] - hq.y) * 0.06)
        wave = [a for a in army if a in S['wave']]
        if wave:
            S['wave'] = set(wave)
            if len(wave) < 0.35 * S['wave_size']:
                for a in wave:
                    self.order_move(a, *rally)
                S['wave'] = set()
                S['wave_n'] = min(22, S['wave_n'] + 3)
            else:
                tgt = self.ai_target(T, wave)
                if tgt:
                    for a in wave:
                        if a.mode == 'idle':
                            self.order_amove(a, tgt.x, tgt.y)
        else:
            ready = [a for a in army if a.mode == 'idle']
            if self.time >= S['grace'] and len(ready) >= S['wave_n'] and (
                    self.power(ready) >= 0.9 * self.power(self.mil(F)) or len(ready) >= 20):
                tgt = self.ai_target(T, ready)
                if tgt:
                    S['wave'], S['wave_size'] = set(ready), len(ready)
                    S['wave_n'] = min(22, S['wave_n'] + 2)
                    for a in ready:
                        self.order_amove(a, tgt.x, tgt.y)
            for a in ready:
                if dist(a.x, a.y, hq.x, hq.y) > 350:
                    self.order_move(a, *rally)

    def ai_target(self, T, group):
        F = 1 - T
        cx = sum(a.x for a in group) / len(group)
        cy = sum(a.y for a in group) / len(group)
        bl = [e for e in self.ents if e.team == F and e.b]
        if not bl:
            return None
        return min(bl, key=lambda e: dist(e.x, e.y, cx, cy) - (150 if e.kind == 'hq' else 0))

    def ai_build(self, T, hq, kind, workers):
        if not self.affordable(T, self.bst[T][kind]['cost']):
            return
        fx, fy = self.bases[1 - T]
        base_ang = math.atan2(fy - hq.y, fx - hq.x)
        for _ in range(25):
            if kind == 'tower':
                a, d = base_ang + random.uniform(-0.9, 0.9), random.uniform(190, 280)
            else:
                a, d = random.uniform(0, 6.283), random.uniform(130, 240)
            b = self.place(T, kind, hq.x + math.cos(a) * d, hq.y + math.sin(a) * d)
            if b:
                free_w = [w for w in workers if w.mode in ('idle', 'harvest')] or workers
                for w in sorted(free_w, key=lambda w: dist(w.x, w.y, b.x, b.y))[:2]:
                    self.order_build(w, b)
                return
