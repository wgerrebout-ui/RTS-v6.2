"""
RTS MÉDIÉVAL v6 - Android (Kivy)
3 factions, escarmouche, campagne (tutoriels + missions), duel réseau, arbre technologique,
intro animée, musique et effets sonores.
"""
import base64
import io
import json
import math
import os
import random
import time
import traceback
import weakref

from kivy.app import App
from kivy.base import ExceptionHandler, ExceptionManager
from kivy.clock import Clock
from kivy.core.image import Image as CoreImage
from kivy.core.window import Window
from kivy.graphics import BorderImage, Color, Line, PopMatrix, PushMatrix, Rectangle, Rotate
from kivy.graphics.texture import Texture
from kivy.metrics import dp
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.screenmanager import FadeTransition, Screen, ScreenManager
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput
from kivy.uix.widget import Widget

import campaign
import net
from assets_data import DATA
from game import ABILITY, DIFF_NAMES, FACTIONS, MAP_H, MAP_W, POP_MAX, Game
from sounds_data import SND

try:
    from kivy.core.audio import SoundLoader
except Exception:
    SoundLoader = None

APP = None
_ERR = set()


# ------------------------------------------------------------------ journal d'erreurs
def log_error(tag='?'):
    try:
        msg = traceback.format_exc()
        key = (tag, msg[-160:])
        if key in _ERR or len(_ERR) > 60:
            return
        _ERR.add(key)
        base = APP.user_data_dir if APP else '.'
        with open(os.path.join(base, 'crash.log'), 'a') as f:
            f.write('[%s] %s\n%s\n' % (time.strftime('%d/%m %H:%M:%S'), tag, msg))
        if APP:
            APP.last_error = msg.strip().splitlines()[-1][:120]
    except Exception:
        pass


class _Handler(ExceptionHandler):
    def handle_exception(self, inst):
        log_error('kivy')
        return ExceptionManager.PASS


# ------------------------------------------------------------------ textures
_T = {}
_missing = set()


def blank_tex():
    t = Texture.create(size=(2, 2), colorfmt='rgba')
    t.blit_buffer(b'\x00' * 16, colorfmt='rgba', bufferfmt='ubyte')
    return t


def tex(name):
    t = _T.get(name)
    if t is None:
        try:
            t = CoreImage(io.BytesIO(base64.b64decode(DATA[name])), ext='png').texture
            t.mag_filter = 'linear'
            t.min_filter = 'linear'
            if name == 'grass':
                t.wrap = 'repeat'
        except Exception:
            if name not in _missing:
                _missing.add(name)
                log_error('texture ' + name)
            t = blank_tex()
        _T[name] = t
    return t


# ------------------------------------------------------------------ réglages + sons
class Settings:
    def __init__(self, path):
        self.path = path
        self.d = dict(sound=True, music=True, quality=1, fps=False, intro=True)
        try:
            with open(path) as f:
                self.d.update(json.load(f))
        except Exception:
            pass

    def __getitem__(self, k):
        return self.d[k]

    def set(self, k, v):
        self.d[k] = v
        try:
            with open(self.path, 'w') as f:
                json.dump(self.d, f)
        except Exception:
            pass


class Snd:
    def __init__(self, folder, settings):
        self.dir, self.st = folder, settings
        self.cache, self.last = {}, {}
        self.cur, self.cur_name = None, None
        try:
            os.makedirs(folder, exist_ok=True)
            for k, v in SND.items():
                p = os.path.join(folder, k + '.ogg')
                data = base64.b64decode(v)
                if not os.path.exists(p) or os.path.getsize(p) != len(data):
                    with open(p, 'wb') as f:
                        f.write(data)
        except Exception:
            log_error('sons')

    def get(self, name):
        if SoundLoader is None:
            return None
        s = self.cache.get(name)
        if s is None:
            try:
                s = SoundLoader.load(os.path.join(self.dir, name + '.ogg'))
            except Exception:
                s = None
            self.cache[name] = s
        return s

    def play(self, name, vol=1.0):
        if not self.st['sound']:
            return
        now = time.time()
        if now - self.last.get(name, 0) < 0.09:
            return
        self.last[name] = now
        try:
            s = self.get(name)
            if s:
                s.volume = max(0.05, min(1.0, vol))
                s.play()
        except Exception:
            log_error('play ' + name)

    def music(self, name, loop=True, vol=0.6):
        try:
            if self.cur_name == name and self.cur and self.cur.state == 'play':
                return
            self.stop_music()
            if not self.st['music']:
                self.cur_name = name
                return
            s = self.get(name)
            if s:
                s.loop = loop
                s.volume = vol
                s.play()
                self.cur, self.cur_name = s, name
        except Exception:
            log_error('musique ' + name)

    def stop_music(self):
        try:
            if self.cur:
                self.cur.stop()
        except Exception:
            pass
        self.cur, self.cur_name = None, None


# ------------------------------------------------------------------ habillage d'interface par faction
SUFFIX = ''
SKIN_SUF = {'kingdom': '_k', 'horde': '_h', 'sylvan': '_s'}
_BG = weakref.WeakSet()


def sk(name):
    n = name + SUFFIX
    return n if (SUFFIX and n in DATA) else name


def attach_bg(w, name, border=24):
    with w.canvas.before:
        Color(1, 1, 1, 1)
        w._bg = BorderImage(texture=tex(sk(name)), border=(border,) * 4, pos=w.pos, size=w.size)
    w._bgname = name
    _BG.add(w)
    w.bind(pos=lambda *_: setattr(w._bg, 'pos', w.pos), size=lambda *_: setattr(w._bg, 'size', w.size))


def set_bg(w, name):
    if w._bgname != name:
        w._bgname = name
        w._bg.texture = tex(sk(name))


def apply_skin(fac):
    global SUFFIX
    SUFFIX = SKIN_SUF.get(fac, '')
    for w in list(_BG):
        try:
            w._bg.texture = tex(sk(w._bgname))
        except Exception:
            pass


# ------------------------------------------------------------------ métriques de sprites
UNIT_META = {
    'worker': dict(w=112, h=112, ax=54, foot=10, top=76),
    'soldier': dict(w=112, h=112, ax=54, foot=10, top=92),
    'archer': dict(w=112, h=112, ax=54, foot=10, top=88),
    'knight': dict(w=160, h=140, ax=75, foot=12, top=122),
    'healer': dict(w=112, h=112, ax=54, foot=10, top=84),
    'heavy': dict(w=160, h=140, ax=78, foot=12, top=124),
}
UNIT_WS = 0.55
BLD_META = {
    'hq': dict(w=224, h=210, base=196, s=0.54),
    'barracks': dict(w=200, h=170, base=156, s=0.50),
    'stable': dict(w=200, h=170, base=156, s=0.50),
    'depot': dict(w=160, h=140, base=126, s=0.48),
    'tower': dict(w=112, h=190, base=178, s=0.60),
    'forge': dict(w=200, h=170, base=156, s=0.50),
    'temple': dict(w=200, h=170, base=156, s=0.50),
    'sanctum': dict(w=200, h=170, base=156, s=0.52),
}
GRASS_WORLD = 230.0
VIEW_WORLD_H = 640
TEAM = {0: (0.25, 0.55, 1.0), 1: (0.93, 0.27, 0.25)}
ROLE = {
    'worker': 'Récolte le bois et le minerai, construit',
    'soldier': 'Corps à corps, solide. Bat le cavalier',
    'archer': 'Tire de loin, fragile. Bat le soldat',
    'knight': "Cavalier rapide. Bat l'archer",
    'healer': 'Soigne les alliés proches. Protégez-le !',
    'heavy': 'Unité lourde : résiste et ravage les bâtiments',
    'hq': 'Votre base : produit des ouvriers, recherches et pouvoir de faction',
    'barracks': 'Produit soldats et archers',
    'stable': 'Produit des cavaliers',
    'depot': 'Dépôt : raccourcit les trajets de récolte',
    'tower': 'Tire sur les ennemis proches',
    'forge': "Recherches d'armes, d'armures et de portée",
    'temple': 'Produit des soigneurs, recherches de soins',
    'sanctum': 'Produit les unités lourdes, recherches de puissance',
}
ROLE_F = {('kingdom', 'heavy'): 'Catapulte : tire de très loin, ravage les bâtiments',
          ('horde', 'heavy'): 'Ogre : massif, ravage tout au corps à corps',
          ('sylvan', 'heavy'): 'Ent : colosse qui se régénère'}

# ------------------------------------------------------------------ petits widgets
class Pic(Widget):
    """Affiche une image en conservant ses proportions."""

    def __init__(self, name=None, pad=0, **kw):
        super().__init__(**kw)
        self.name = name
        self.pad = pad
        self.bind(pos=self.rd, size=self.rd)
        self.rd()

    def set(self, name):
        if name != self.name:
            self.name = name
            self.rd()

    def rd(self, *a):
        self.canvas.clear()
        if not self.name or self.width < 2:
            return
        t = tex(self.name)
        w, h = t.size
        k = min((self.width - 2 * self.pad) / w, (self.height - 2 * self.pad) / h)
        dw, dh = w * k, h * k
        with self.canvas:
            Color(1, 1, 1, 1)
            Rectangle(texture=t, pos=(self.center_x - dw / 2, self.center_y - dh / 2), size=(dw, dh))


class ToolBtn(ButtonBehavior, FloatLayout):
    def __init__(self, icon, caption, **kw):
        super().__init__(**kw)
        attach_bg(self, 'ui_btn')
        self.pic = Pic(icon, pad=dp(3), size_hint=(1, .66), pos_hint={'x': 0, 'top': .97})
        self.lab = Label(text=caption, font_size=dp(9.5), size_hint=(1, .3), pos_hint={'x': 0, 'y': .02},
                         color=(1, 1, 1, 1), bold=True)
        self.add_widget(self.pic)
        self.add_widget(self.lab)
        self.on = False
        self.bind(state=lambda *_: self.restyle())

    def restyle(self):
        set_bg(self, 'ui_btn_on' if self.on else ('ui_btn_down' if self.state == 'down' else 'ui_btn'))

    def set_on(self, on):
        if on != self.on:
            self.on = on
            self.restyle()


class Card(ButtonBehavior, FloatLayout):
    """Carte d'action : icône, nom, coût, état (acquis / en cours / verrouillé / recharge)."""

    def __init__(self, label, cost, icon, desc='', **kw):
        super().__init__(**kw)
        attach_bg(self, 'ui_card')
        self.ok, self.desc, self.long, self._ev, self.info = True, desc, False, None, ''
        col = BoxLayout(orientation='vertical', padding=(dp(3), dp(2)), spacing=dp(1), size_hint=(1, 1))
        self.pic = Pic(icon, pad=dp(1), size_hint=(1, .48))
        self.name = Label(text=label, font_size=dp(10), bold=True, size_hint=(1, .28), color=(1, 1, 1, 1), halign='center', valign='middle')
        self.name.bind(size=lambda w, s: setattr(w, 'text_size', s))
        row = BoxLayout(size_hint=(1, .24), spacing=dp(1))
        self.costs = []
        for ic, v in (('i_wood', cost[0]), ('i_ore', cost[1])):
            if v:
                row.add_widget(Pic(ic, size_hint=(None, 1), width=dp(13)))
                lb = Label(text=str(v), font_size=dp(10.5), size_hint=(.5, 1), color=(1, 1, 1, 1), bold=True)
                row.add_widget(lb)
                self.costs.append(lb)
        col.add_widget(self.pic)
        col.add_widget(self.name)
        col.add_widget(row)
        self.add_widget(col)
        self.over = Label(text='', font_size=dp(11), bold=True, size_hint=(1, .26), pos_hint={'x': 0, 'center_y': .5}, color=(1, .95, .6, 1), opacity=0)
        with self.over.canvas.before:
            Color(0, 0, 0, .62)
            self._ob = Rectangle(pos=self.over.pos, size=self.over.size)
        self.over.bind(pos=lambda *_: setattr(self._ob, 'pos', self.over.pos), size=lambda *_: setattr(self._ob, 'size', self.over.size))
        self.add_widget(self.over)
        self.bind(state=lambda *_: self.on_state())

    def on_state(self):
        if self.state == 'down':
            self.long = False
            self._ev = Clock.schedule_once(self.fire_long, 0.55)
        elif self._ev:
            self._ev.cancel()
            self._ev = None
        self.restyle()

    def fire_long(self, dt):
        self.long = True
        if APP and self.desc:
            APP.g.say(self.desc)

    def restyle(self):
        if not self.ok:
            set_bg(self, 'ui_btn_bad')
        else:
            set_bg(self, 'ui_btn_down' if self.state == 'down' else 'ui_card')

    def set_ok(self, ok):
        if ok != self.ok:
            self.ok = ok
            for lb in self.costs:
                lb.color = (1, 1, 1, 1) if ok else (1, .55, .55, 1)
            self.restyle()

    def set_info(self, text, dim=False):
        if text != self.info:
            self.info = text
            self.over.text = text
            self.over.opacity = 1 if text else 0
        self.opacity = 0.62 if dim else 1


# ------------------------------------------------------------------ widgets de menu
# ------------------------------------------------------------------ widgets de menu
def lbl(text, fs=14, bold=False, color=(1, 1, 1, 1), halign='center', valign='middle', **kw):
    l = Label(text=text, font_size=dp(fs), bold=bold, color=color, halign=halign, valign=valign, markup=True, **kw)
    l.bind(size=lambda w, s: setattr(w, 'text_size', s))
    return l


class BigBtn(ButtonBehavior, BoxLayout):
    def __init__(self, text, icon=None, sub='', style='ui_btn', size=17, **kw):
        super().__init__(orientation='horizontal', padding=(dp(10), dp(5)), spacing=dp(8), **kw)
        attach_bg(self, style)
        self.style = style
        if icon:
            self.add_widget(Pic(icon, pad=dp(2), size_hint=(None, 1), width=dp(50)))
        col = BoxLayout(orientation='vertical')
        al = 'left' if icon else 'center'
        self.title = lbl(text, size, True, halign=al)
        col.add_widget(self.title)
        if sub:
            self.sub = lbl(sub, 11, color=(.82, .88, 1, 1), halign=al, valign='top')
            col.add_widget(self.sub)
        self.add_widget(col)
        self.bind(state=lambda *_: self.restyle())

    def restyle(self):
        set_bg(self, 'ui_btn_down' if self.state == 'down' else self.style)

    def set_style(self, s):
        self.style = s
        self.restyle()


class FacCard(ButtonBehavior, BoxLayout):
    def __init__(self, fac, extra='', **kw):
        super().__init__(orientation='horizontal', padding=dp(6), spacing=dp(6), **kw)
        attach_bg(self, 'ui_card')
        self.fac, self.sel = fac, False
        self.add_widget(Pic('em_' + fac, size_hint=(None, 1), width=dp(46)))
        col = BoxLayout(orientation='vertical')
        f = FACTIONS[fac]
        col.add_widget(lbl(f['name'], 13, True, halign='left', size_hint=(1, .3)))
        self.trait = lbl(f['trait'] + extra, 10, color=(.86, .91, 1, 1), halign='left', valign='top', size_hint=(1, .7))
        col.add_widget(self.trait)
        self.add_widget(col)
        self.bind(state=lambda *_: self.restyle())

    def restyle(self):
        set_bg(self, 'ui_btn_on' if self.sel else ('ui_btn_down' if self.state == 'down' else 'ui_card'))

    def select(self, on):
        self.sel = on
        self.restyle()


class FacRow(BoxLayout):
    def __init__(self, value, on_change=None, **kw):
        super().__init__(orientation='horizontal', spacing=dp(6), **kw)
        self.value, self.on_change, self.cards = value, on_change, {}
        for fac in FACTIONS:
            c = FacCard(fac)
            c.bind(on_release=lambda *_, f=fac: self.pick(f))
            self.cards[fac] = c
            self.add_widget(c)
        self.pick(value, False)

    def pick(self, fac, notify=True):
        self.value = fac
        for f, c in self.cards.items():
            c.select(f == fac)
        if notify and self.on_change:
            self.on_change(fac)


class ChoiceRow(BoxLayout):
    def __init__(self, options, value, on_change=None, **kw):
        super().__init__(orientation='horizontal', spacing=dp(6), **kw)
        self.value, self.on_change, self.btns = value, on_change, {}
        for val, text in options:
            b = BigBtn(text, size=14)
            b.bind(on_release=lambda *_, v=val: self.pick(v))
            self.btns[val] = b
            self.add_widget(b)
        self.pick(value, False)

    def pick(self, v, notify=True):
        self.value = v
        for k, b in self.btns.items():
            b.set_style('ui_btn_on' if k == v else 'ui_btn')
        if notify and self.on_change:
            self.on_change(v)


class Backdrop(Widget):
    """Fond des menus : herbe, ombrage et décor des trois factions."""

    def __init__(self, **kw):
        super().__init__(**kw)
        self.bind(pos=self.rd, size=self.rd)

    def rd(self, *a):
        self.canvas.clear()
        w, h = self.size
        if w < 10:
            return
        T = dp(210)
        with self.canvas:
            Color(1, 1, 1, 1)
            Rectangle(texture=tex('grass'), pos=self.pos, size=self.size, tex_coords=(0, 0, w / T, 0, w / T, h / T, 0, h / T))
            Color(0, 0, 0, 0.42)
            Rectangle(pos=self.pos, size=self.size)
            k = h / 640.0
            for name, fx, fy, s in (('b_kingdom_hq_0', .09, .01, .85), ('b_horde_hq_1', .91, .01, .85), ('b_sylvan_hq_0', .5, -.02, .7),
                                    ('u_kingdom_soldier_0_idle', .24, .02, .9), ('u_horde_soldier_1_idle', .76, .02, .9),
                                    ('u_sylvan_archer_0_idle', .39, .0, .9), ('u_horde_knight_1_idle', .64, .0, .85)):
                t = tex(name)
                ww, hh = t.width * k * s * 1.25, t.height * k * s * 1.25
                Color(1, 1, 1, .92)
                Rectangle(texture=t, pos=(self.x + w * fx - ww / 2, self.y + h * fy), size=(ww, hh))


def panel(content_hint=(.95, .94)):
    b = BoxLayout(orientation='vertical', spacing=dp(6), padding=dp(10), size_hint=content_hint,
                  pos_hint={'center_x': .5, 'center_y': .5})
    attach_bg(b, 'ui_panel', 20)
    return b


class Page(Screen):
    def __init__(self, app, name, **kw):
        super().__init__(name=name, **kw)
        self.app = app
        self.root_f = FloatLayout()
        self.root_f.add_widget(Backdrop())
        self.add_widget(self.root_f)


def nav(app, back, go_text=None, go_fn=None, go_style='ui_btn_on'):
    row = BoxLayout(size_hint=(1, None), height=dp(46), spacing=dp(10))
    b = BigBtn('Retour', 'i_home', size=15)
    b.bind(on_release=lambda *_: app.go(back))
    row.add_widget(b)
    if go_text:
        g = BigBtn(go_text, 'i_play', style=go_style, size=15)
        g.bind(on_release=lambda *_: go_fn())
        row.add_widget(g)
    return row




# ------------------------------------------------------------------ vue du jeu
AMBIENT = {  # (faction, bâtiment) -> (couleur, mode)
    ('kingdom', 'forge'): ((.75, .75, .8), 'smoke'), ('horde', 'forge'): ((1, .5, .2), 'ember'), ('sylvan', 'forge'): ((.6, 1, .9), 'mote'),
    ('kingdom', 'temple'): ((1, .9, .5), 'mote'), ('horde', 'temple'): ((.5, 1, .5), 'ember'), ('sylvan', 'temple'): ((.6, .9, 1), 'mote'),
    ('horde', 'hq'): ((1, .5, .2), 'ember'), ('sylvan', 'hq'): ((.6, 1, .7), 'mote'), ('kingdom', 'hq'): ((.85, .85, .9), 'smoke'),
    ('sylvan', 'sanctum'): ((.5, 1, .6), 'mote'), ('horde', 'sanctum'): ((1, .4, .2), 'ember'), ('kingdom', 'sanctum'): ((.8, .8, .85), 'smoke'),
    ('horde', 'tower'): ((1, .5, .2), 'ember'), ('sylvan', 'tower'): ((.6, 1, .9), 'mote'),
}
PROPS = {'kingdom': ['k_hay', 'k_fence', 'k_field', 'k_banner', 'k_barrel'], 'horde': ['h_bones', 'h_pike', 'h_spikes', 'h_brazier', 'h_tent'],
         'sylvan': ['s_shroom', 's_crystal', 's_stones', 's_flowers', 's_stump']}
DIRT = {'kingdom': 'dirt_k', 'horde': 'dirt_h', 'sylvan': 'dirt_s'}
TECH_ICON_FALLBACK = 't_star'


class GameView(Widget):
    def __init__(self, g, app, **kw):
        super().__init__(**kw)
        self.g, self.app = g, app
        self.rect_mode = False
        self.zoom = 1.0
        self.touches = {}
        self.pinch0 = None
        self.pinching = False
        self.start = self.cur = None
        self.moved = False
        self.dbl = False
        self.mm_drag = False
        self.ghost = None
        self.net = None
        self.need_center = True
        self.rings = []
        self.flash = None
        self.over_done = False
        self.t = 0.0
        self.make_decor()
        Clock.schedule_interval(self.tick, 1 / 30)

    def make_decor(self):
        rnd = random.Random(7)
        names = ['tuft_0', 'tuft_1', 'tuft_2', 'flower_0', 'flower_1', 'flower_2', 'flower_3']
        self.decor = []
        for _ in range(420):
            n = rnd.choice(names) if rnd.random() < .6 else rnd.choice(names[:3])
            self.decor.append((rnd.uniform(30, MAP_W - 30), rnd.uniform(30, MAP_H - 30), n))
        self.props = []
        g = self.g
        for t, (bx, by) in g.bases.items():
            r2 = random.Random(int(bx * 3 + by))
            fac = g.fac[t]
            for i in range(16):
                a = r2.uniform(0, 6.283)
                d = r2.uniform(190, 330)
                x, y = bx + math.cos(a) * d, by + math.sin(a) * d
                if 40 < x < MAP_W - 40 and 40 < y < MAP_H - 40:
                    self.props.append((x, y, 'prop_' + r2.choice(PROPS[fac])))

    # ---- conversions
    @property
    def sc(self):
        return max(1.0, self.height) / VIEW_WORLD_H * self.zoom

    def w2s(self, x, y):
        return (x - self.g.cam[0]) * self.sc, self.height - (y - self.g.cam[1]) * self.sc

    def s2w(self, sx, sy):
        return sx / self.sc + self.g.cam[0], (self.height - sy) / self.sc + self.g.cam[1]

    def view_world(self):
        return self.width / self.sc, self.height / self.sc

    def clamp_cam(self):
        vw, vh = self.view_world()
        c = self.g.cam
        c[0] = max(0, min(max(0, MAP_W - vw), c[0]))
        c[1] = max(0, min(max(0, MAP_H - vh), c[1]))

    def mm_rect(self):
        w = self.width * 0.17
        h = w * MAP_H / MAP_W
        return self.width - w - dp(8), self.height - h - dp(44), w, h

    def center_on(self, x, y):
        vw, vh = self.view_world()
        self.g.cam = [x - vw / 2, y - vh / 2]

    # ---- réseau
    def net_pump(self):
        n, g = self.net, self.g
        if not n:
            return
        p = n['peer']
        if n['role'] == 'host':
            for m in p.poll():
                if m['k'] == 'cmd':
                    g.exec_cmd(1, m['c'])
                elif m['k'] == 'bye' and g.winner is None:
                    g.set_winner(0, 'Votre adversaire a quitté la partie.')
            n['t'] += 1
            if n['t'] % (3 if g.winner is None else 12) == 0:
                p.send({'k': 'snap', 's': g.snapshot()})
        else:
            for m in p.poll():
                if m['k'] == 'snap':
                    g.apply_snapshot(m['s'])
                elif m['k'] == 'bye' and g.winner is None:
                    g.set_winner(g.me, 'Votre adversaire a quitté la partie.')
            for c in g.outbox:
                p.send({'k': 'cmd', 'c': c})
            g.outbox = []
        if not p.alive and g.winner is None and g.over is None:
            g.winner, g.over, g.reason = -1, 'CONNEXION PERDUE', "Le lien avec l'autre téléphone a été coupé."

    # ---- boucle
    def tick(self, dt):
        if self.app.sm.current != 'game':
            return
        g = self.g
        self.t += dt
        if self.need_center and self.width > 300:
            self.center_on(*g.focus_base())
            self.need_center = False
        if not g.paused and not g.over:
            g.update(min(dt, 0.05))
        self.net_pump()
        self.clamp_cam()
        if g.placing and self.ghost is None:
            vw, vh = self.view_world()
            self.ghost = (g.cam[0] + vw / 2, g.cam[1] + vh / 2)
        if not g.placing:
            self.ghost = None
        self.handle_events()
        if g.over and not self.over_done:
            self.over_done = True
            self.app.snd.play('sfx_win' if g.winner == g.me else 'sfx_lose')
            self.app.snd.stop_music()
        try:
            self.draw()
        except Exception:
            log_error('draw')

    def handle_events(self):
        g, snd = self.g, self.app.snd
        if not g.events:
            return
        vw, vh = self.view_world()
        for name, x, y, team in g.events:
            onscreen = g.cam[0] - 60 < x < g.cam[0] + vw + 60 and g.cam[1] - 60 < y < g.cam[1] + vh + 60
            if name in ('build', 'research', 'step'):
                if team == g.me:
                    snd.play('sfx_build' if name == 'build' else 'sfx_research')
            elif name == 'ability':
                snd.play('sfx_ability')
                hq = next((e for e in g.ents if e.kind == 'hq' and e.team == team), None)
                if hq:
                    col = {'kingdom': (1, .85, .35), 'horde': (1, .35, .2), 'sylvan': (.5, 1, .7)}[g.fac[team]]
                    self.rings.append((hq.x, hq.y, self.t, col))
                    if team == g.me:
                        self.flash = (self.t, col)
            elif onscreen:
                if name == 'hit':
                    snd.play('sfx_hit', .7)
                elif name == 'arrow':
                    snd.play('sfx_arrow', .5)
                elif name == 'death':
                    snd.play('sfx_death', .6)
                elif name == 'heal':
                    snd.play('sfx_heal', .4)
        g.events.clear()

    # ---- primitives
    def blit(self, name, x, y, w, h, flip=False, col=(1, 1, 1, 1)):
        Color(*col)
        if flip:
            Rectangle(texture=tex(name), pos=(x, y), size=(w, h), tex_coords=(1, 0, 0, 0, 0, 1, 1, 1))
        else:
            Rectangle(texture=tex(name), pos=(x, y), size=(w, h))

    def rect(self, x, y, w, h):
        Rectangle(pos=(x, y), size=(w, h))

    # ---- dessin
    def draw(self):
        g, sc = self.g, self.sc
        hi = self.app.settings['quality'] >= 1
        self.canvas.clear()
        with self.canvas:
            Color(0.06, 0.09, 0.07)
            self.rect(0, 0, self.width, self.height)
            self.draw_terrain(hi)
            for c in g.corpses:
                try:
                    self.draw_corpse(c, sc)
                except Exception:
                    log_error('corpse')
            items = [(r.y, 0, r) for r in g.res]
            items += [(e.y + (e.r * .45 if e.b else 0), 1, e) for e in g.ents]
            items += [(rk[1], 2, rk) for rk in g.rocks]
            items.sort(key=lambda t: t[0])
            vis = dp(160)
            for _, kind, o in items:
                sx, sy = self.w2s(o[0], o[1]) if kind == 2 else self.w2s(o.x, o.y)
                if sx < -vis or sx > self.width + vis or sy < -vis or sy > self.height + vis:
                    continue
                try:
                    if kind == 0:
                        self.draw_resource(o, sx, sy, sc)
                    elif kind == 2:
                        self.draw_rock(o, sx, sy, sc)
                    elif o.b:
                        self.draw_building(o, sx, sy, sc, hi)
                    else:
                        self.draw_unit(o, sx, sy, sc)
                except Exception:
                    log_error('item %s' % getattr(o, 'kind', '?'))
            self.draw_fx(sc)
            self.draw_rings(sc)
            if g.placing and self.ghost:
                self.draw_ghost(sc)
            if self.rect_mode and self.start and self.cur and self.moved:
                x0, y0 = self.start
                x1, y1 = self.cur
                Color(0.4, 1, 0.4, 0.15)
                self.rect(min(x0, x1), min(y0, y1), abs(x1 - x0), abs(y1 - y0))
                Color(0.5, 1, 0.5)
                Line(rectangle=(min(x0, x1), min(y0, y1), abs(x1 - x0), abs(y1 - y0)), width=1.6)
            if hi:
                self.blit('vignette', 0, 0, self.width, self.height, col=(1, 1, 1, .55))
            if self.flash:
                a = 0.28 - (self.t - self.flash[0]) * 0.28
                if a > 0:
                    Color(self.flash[1][0], self.flash[1][1], self.flash[1][2], a)
                    self.rect(0, 0, self.width, self.height)
                else:
                    self.flash = None
            self.draw_minimap()

    def draw_terrain(self, hi):
        g, sc = self.g, self.sc
        sx0, sy0 = self.w2s(0, MAP_H)
        mw, mh = MAP_W * sc, MAP_H * sc
        x0, y0 = max(0, sx0), max(0, sy0)
        x1, y1 = min(self.width, sx0 + mw), min(self.height, sy0 + mh)
        if x1 <= x0 or y1 <= y0:
            return
        wx0, wy1 = self.s2w(x0, y0)
        wx1, wy0 = self.s2w(x1, y1)
        T = GRASS_WORLD
        u0, u1, vb, vt = wx0 / T, wx1 / T, -wy1 / T, -wy0 / T
        Color(1, 1, 1, 1)
        Rectangle(texture=tex('grass'), pos=(x0, y0), size=(x1 - x0, y1 - y0), tex_coords=(u0, vb, u1, vb, u1, vt, u0, vt))
        for t, (bx, by) in g.bases.items():
            cx, cy = self.w2s(bx, by)
            R = 340 * sc
            self.blit(DIRT[g.fac[t]], cx - R, cy - R, 2 * R, 2 * R)
        for px, py, r in g.ponds:
            sx, sy = self.w2s(px, py)
            w = r * 2.4 * sc
            h = w * 120 / 170
            if -w < sx < self.width + w and -h < sy < self.height + h:
                self.blit('pond_%d' % (int(px + py) % 3), sx - w / 2, sy - h * .55, w, h)
                if hi:
                    for k in range(3):
                        ph = (self.t * .35 + k / 3.0 + px * .001) % 1.0
                        self.blit('sparkle', sx + (ph - .5) * w * .6, sy - h * .1 + math.sin(ph * 6.28 + k) * h * .12, 14 * sc, 14 * sc, col=(1, 1, 1, .6 * math.sin(ph * 3.14)))
        if hi:
            for x, y, n in self.decor:
                sx, sy = self.w2s(x, y)
                if -40 < sx < self.width + 40 and -40 < sy < self.height + 40:
                    t = tex(n)
                    k = .55 * sc
                    self.blit(n, sx - t.width * k / 2, sy - 2 * k, t.width * k, t.height * k)
            for x, y, n in self.props:
                sx, sy = self.w2s(x, y)
                if -90 < sx < self.width + 90 and -90 < sy < self.height + 90:
                    t = tex(n)
                    k = .62 * sc
                    self.blit(n, sx - t.width * k / 2, sy - 3 * k, t.width * k, t.height * k)
                    if n.endswith('brazier'):
                        self.blit('light_warm', sx - 40 * sc, sy - 10 * sc, 80 * sc, 80 * sc, col=(1, 1, 1, .5 + .2 * math.sin(self.t * 9 + x)))
        Color(0.05, 0.08, 0.05, 1)
        Line(rectangle=(sx0, sy0, mw, mh), width=3)

    def draw_rock(self, rk, sx, sy, sc):
        x, y, r = rk
        w = r * 2.7 * sc
        h = w * .8
        self.blit('rock_%d' % (int(x * 3 + y) % 3), sx - w / 2, sy - h * .22 - r * .5 * sc, w, h)

    def draw_resource(self, o, sx, sy, sc):
        k = 0.65 + 0.35 * min(1, o.amount / o.max)
        if o.kind == 'wood':
            n = 'tree_%d' % (int(o.x * 7 + o.y * 13) % 3)
            w, h = 96 * .46 * sc * k, 130 * .46 * sc * k
            sway = math.sin(self.t * 1.3 + o.x) * 1.2 * sc
            self.blit(n, sx - w / 2 + sway * .3, sy - h * .07 - 4 * sc, w, h)
        else:
            n = 'ore_%d' % (int(o.x * 5 + o.y * 11) % 2)
            w, h = 92 * .5 * sc * k, 80 * .5 * sc * k
            self.blit(n, sx - w / 2, sy - h * .12 - 4 * sc, w, h)
            if self.app.settings['quality'] >= 1:
                a = .5 + .5 * math.sin(self.t * 3 + o.x)
                self.blit('sparkle', sx + 6 * sc, sy + h * .3, 12 * sc, 12 * sc, col=(1, 1, 1, a * .8))

    def draw_corpse(self, c, sc):
        sx, sy = self.w2s(c['x'], c['y'])
        m = UNIT_META[c['kind']]
        sf = UNIT_WS * sc
        a = max(0.0, min(1.0, c['life'] / 1.8)) * .85
        f = 1 if math.cos(c['ang']) >= 0 else -1
        PushMatrix()
        Rotate(angle=-80 * f, origin=(sx, sy))
        x = sx - (m['ax'] if f > 0 else m['w'] - m['ax']) * sf
        self.blit('u_%s_%s_%d_idle' % (self.g.fac[c['team']], c['kind'], c['team']), x, sy - m['foot'] * sf, m['w'] * sf, m['h'] * sf, flip=(f < 0), col=(.7, .7, .7, a))
        PopMatrix()

    def hp_bar(self, e, cx, y, w):
        if e not in self.g.sel and e.hp >= e.maxhp:
            return
        f = max(0, min(1, e.hp / e.maxhp))
        Color(0, 0, 0, 0.8)
        self.rect(cx - w / 2 - 2, y - 2, w + 4, 9)
        Color(0.3, 0.06, 0.06)
        self.rect(cx - w / 2, y, w, 5)
        Color(1 - f, 0.25 + 0.7 * f, 0.15)
        self.rect(cx - w / 2, y, w * f, 5)
        Color(1, 1, 1, 0.3)
        self.rect(cx - w / 2, y + 3, w * f, 2)

    def draw_unit(self, e, sx, sy, sc):
        g = self.g
        m = UNIT_META[e.kind]
        sf = UNIT_WS * sc
        f = 1 if math.cos(e.ang) >= 0 else -1
        ph = hash(id(e)) % 10
        t = g.time
        if e.flash > 0:
            fr = 'atk'
        elif e.working:
            fr = 'atk' if int((t + ph * .1) * 4) % 2 == 0 else 'idle'
        elif e.moving:
            fr = 'walk1' if int((t + ph * .05) * 5.5) % 2 == 0 else 'walk2'
        else:
            fr = 'idle'
        rw = e.r * 3.0 * sc
        self.blit('ring_t%d' % e.team, sx - rw / 2, sy - rw / 4, rw, rw / 2)
        if e in g.sel:
            sw = e.r * 3.7 * sc
            self.blit('ring_sel' if e.team == g.me else 'ring_sel_e', sx - sw / 2, sy - sw / 4, sw, sw / 2)
        if g.ab_t[e.team] > 0 and e.kind != 'worker':
            col = {'kingdom': (1, .85, .3), 'horde': (1, .3, .15), 'sylvan': (.4, 1, .6)}[g.fac[e.team]]
            aw = e.r * 4.2 * sc
            self.blit('light_warm', sx - aw / 2, sy - aw / 4, aw, aw / 2, col=(col[0], col[1], col[2], .55 + .25 * math.sin(self.t * 8)))
        breathe = 1 + (math.sin(self.t * 2.4 + ph) * .012 if fr == 'idle' else 0)
        w, h = m['w'] * sf, m['h'] * sf * breathe
        lunge = (e.flash / .15) * 5 * sf * f if (e.flash > 0 and e.d['rng'] < 60) else 0
        x = sx - (m['ax'] if f > 0 else m['w'] - m['ax']) * sf + lunge
        y = sy - m['foot'] * sf
        self.blit('u_%s_%s_%d_%s' % (g.fac[e.team], e.kind, e.team, fr), x, y, w, h, flip=(f < 0))
        if e.kind == 'worker' and e.carry:
            cn = 'carry_ore' if e.ctype == 'ore' else 'carry_wood'
            cs = 30 * sf
            self.blit(cn, sx - f * 20 * sf - cs / 2, sy + 22 * sf, cs, cs * (.7 if cn == 'carry_wood' else 1))
        if e.kind == 'healer' and e.working and self.app.settings['quality'] >= 1:
            self.blit('light_cool', sx - 30 * sf, sy + 10 * sf, 60 * sf, 60 * sf, col=(.6, 1, .7, .7))
        self.hp_bar(e, sx, sy + m['top'] * sf + 6, max(34 * sf, 26))

    def ambient(self, e, sx, base_y, w, h, sc):
        spec = AMBIENT.get((self.g.fac[e.team], e.kind))
        if not spec or not e.built:
            return
        col, mode = spec
        ox = {'forge': .28, 'hq': 0.0, 'temple': 0.0, 'sanctum': 0.0, 'tower': 0.0}.get(e.kind, 0.0)
        for i in range(5):
            ph = (self.t * (.35 if mode == 'smoke' else .6) + i / 5.0 + e.id * .137) % 1.0
            if mode == 'smoke':
                x = sx + ox * w + math.sin(ph * 5 + i) * 6 * sc
                y = base_y + h * .78 + ph * 55 * sc
                sz = (10 + ph * 22) * sc
                self.blit('puff', x - sz / 2, y - sz / 2, sz, sz, col=(col[0], col[1], col[2], (1 - ph) * .35))
            else:
                x = sx + (math.sin(i * 2.3 + e.id) * .35) * w + math.sin(ph * 6 + i) * 8 * sc
                y = base_y + h * (.25 if mode == 'mote' else .6) + ph * 70 * sc
                sz = (7 if mode == 'ember' else 9) * sc
                self.blit('sparkle', x - sz / 2, y - sz / 2, sz, sz, col=(col[0], col[1], col[2], math.sin(ph * 3.14) * .9))

    def draw_building(self, e, sx, sy, sc, hi):
        g = self.g
        m = BLD_META[e.kind]
        s = m['s'] * sc
        w, h = m['w'] * s, m['h'] * s
        base_y = sy - e.r * .45 * sc
        x = sx - w / 2
        y = base_y - (m['h'] - m['base']) * s
        fac = g.fac[e.team]
        if e in g.sel:
            rw = e.r * 3.3 * sc
            self.blit('ring_sel' if e.team == g.me else 'ring_sel_e', sx - rw / 2, base_y - rw / 4, rw, rw / 2)
        name = 'b_%s_%s_%d' % (fac, e.kind, e.team)
        if e.built:
            self.blit(name, x, y, w, h)
            if hi:
                self.ambient(e, sx, y, w, h, sc)
        else:
            prog = min(1, e.bt / e.d['time'])
            rise = (1 - prog) * h * .25
            self.blit(name, x, y - rise, w, h, col=(1, 1, 1, .3 + .7 * prog))
            sw, sh = 200 * s, 170 * s
            self.blit('scaffold', sx - sw / 2, base_y - 14 * s, sw, sh, col=(1, 1, 1, .95 - .5 * prog))
            Color(0, 0, 0, 0.8)
            self.rect(sx - 44 * sc, y + h + 6, 88 * sc, 10)
            Color(1, 0.8, 0.2)
            self.rect(sx - 42 * sc, y + h + 8, 84 * sc * prog, 6)
            if hi and int(self.t * 6) % 3 == 0:
                self.blit('puff', sx + math.sin(self.t * 13) * w * .4 - 8 * sc, base_y - 6 * sc, 16 * sc, 16 * sc, col=(.8, .7, .5, .5))
        if e.built and e.queue:
            prog = e.qt / g.ust[e.team][e.queue[0]]['time']
            self.blit('ic_%s_%s_%d' % (fac, e.queue[0], e.team), sx - 40 * sc, base_y - 30 * sc, 24 * sc, 24 * sc)
            Color(0, 0, 0, 0.8)
            self.rect(sx - 12 * sc, base_y - 22 * sc, 52 * sc, 10)
            Color(0.95, 0.95, 0.95)
            self.rect(sx - 10 * sc, base_y - 20 * sc, 48 * sc * min(1, prog), 6)
            for i in range(len(e.queue) - 1):
                Color(1, 1, 1, .9)
                self.rect(sx + 44 * sc + i * 8 * sc, base_y - 22 * sc, 5 * sc, 5 * sc)
        if e.built and e.res:
            t = g.tech(e.team, e.res[0])
            self.blit(t['icon'], sx - 12 * sc, y + h + 4 * sc, 24 * sc, 24 * sc)
            Color(0, 0, 0, 0.8)
            self.rect(sx - 36 * sc, y + h - 4 * sc, 72 * sc, 8)
            Color(0.5, 0.85, 1)
            self.rect(sx - 35 * sc, y + h - 3 * sc, 70 * sc * min(1, e.res[1] / t['time']), 6)
        if e in g.sel:
            if 'rng' in e.d:
                Color(1, 1, 1, 0.4)
                Line(circle=(sx, sy, e.d['rng'] * sc), width=1.4)
            if e.rally and e.team == g.me:
                rx, ry = self.w2s(*e.rally)
                Color(0.4, 1, 0.4)
                Line(points=[sx, sy, rx, ry], width=1.2)
                self.blit('ring_sel', rx - 20, ry - 10, 40, 20)
        self.hp_bar(e, sx, y + h * (.99 if e.kind != 'tower' else .96) + 4, max(70 * sc * m['s'], 44))

    def draw_ghost(self, sc):
        g = self.g
        k = g.placing
        m = BLD_META[k]
        d = g.bst[g.me][k]
        s = m['s'] * sc
        gx, gy = self.w2s(*self.ghost)
        ok = g.can_place(g.me, k, *self.ghost)
        base_y = gy - d['r'] * .45 * sc
        col = (0.5, 1, 0.5, .8) if ok else (1, 0.45, 0.45, .8)
        rw = d['r'] * 3.0 * sc
        self.blit('ring_sel' if ok else 'ring_sel_e', gx - rw / 2, base_y - rw / 4, rw, rw / 2)
        self.blit('b_%s_%s_%d' % (g.fac[g.me], k, g.me), gx - m['w'] * s / 2, base_y - (m['h'] - m['base']) * s, m['w'] * s, m['h'] * s, col=col)
        if 'rng' in d:
            Color(1, 1, 1, 0.35)
            Line(circle=(gx, gy, d['rng'] * sc), width=1.4)

    def draw_fx(self, sc):
        for f in self.g.fx:
            k = f['life'] / f['max']
            if f['t'] == 'p':
                sx, sy = self.w2s(f['x'], f['y'])
                sz = f['size'] * sc * (3.2 + 4 * (1 - k))
                c = f['col']
                self.blit('puff', sx - sz / 2, sy - sz / 2, sz, sz, col=(c[0], c[1], c[2], k * .9))
            else:
                p = 1 - k
                kind = f.get('p', 'arrow')
                ax, ay = f['x'] + (f['x1'] - f['x']) * p, f['y'] + (f['y1'] - f['y']) * p
                sx, sy = self.w2s(ax, ay)
                if kind == 'rock':
                    sy += math.sin(p * 3.14159) * 70 * sc
                    sz = 20 * sc
                    self.blit('proj_rock', sx - sz / 2, sy + 22 * sc - sz / 2, sz, sz)
                elif kind == 'orb':
                    for j in range(3):
                        pj = max(0, p - j * .08)
                        ox, oy = self.w2s(f['x'] + (f['x1'] - f['x']) * pj, f['y'] + (f['y1'] - f['y']) * pj)
                        sz = (30 - j * 7) * sc
                        self.blit('proj_orb', ox - sz / 2, oy + 22 * sc - sz / 2, sz, sz, col=(1, 1, 1, 1 - j * .3))
                else:
                    s0x, s0y = self.w2s(f['x'], f['y'])
                    s1x, s1y = self.w2s(f['x1'], f['y1'])
                    ang = math.degrees(math.atan2(s1y - s0y, s1x - s0x))
                    PushMatrix()
                    Rotate(angle=ang, origin=(sx, sy + 22 * sc))
                    self.blit('arrow' if kind == 'arrow' else 'proj_bolt', sx - 18 * sc, sy + 22 * sc - 4 * sc, 36 * sc, 8 * sc)
                    PopMatrix()

    def draw_rings(self, sc):
        keep = []
        for (x, y, t0, col) in self.rings:
            a = (self.t - t0) / 1.3
            if a >= 1:
                continue
            keep.append((x, y, t0, col))
            sx, sy = self.w2s(x, y)
            sz = (60 + a * 900) * sc
            self.blit('ring_sel', sx - sz / 2, sy - sz / 4, sz, sz / 2, col=(col[0], col[1], col[2], (1 - a) * .9))
        self.rings = keep

    def draw_minimap(self):
        g, sc = self.g, self.sc
        mx, my, mw, mh = self.mm_rect()
        Color(0, 0, 0, 0.7)
        self.rect(mx - 4, my - 4, mw + 8, mh + 8)
        Color(0.25, 0.45, 0.25)
        self.rect(mx, my, mw, mh)
        for t, (bx, by) in g.bases.items():
            Color(0.55, 0.43, 0.3, .8)
            self.rect(mx + (bx - 150) / MAP_W * mw, my + mh - (by + 150) / MAP_H * mh, 300 / MAP_W * mw, 300 / MAP_H * mh)
        for px, py, r in g.ponds:
            Color(0.2, 0.5, 0.85)
            self.rect(mx + (px - r) / MAP_W * mw, my + mh - (py + r) / MAP_H * mh, 2 * r / MAP_W * mw, 2 * r / MAP_H * mh)
        for x, y, r in g.rocks:
            Color(0.6, 0.6, 0.65)
            self.rect(mx + x / MAP_W * mw, my + mh - y / MAP_H * mh, 2.5, 2.5)
        for r in g.res:
            Color(0.1, 0.45, 0.2) if r.kind == 'wood' else Color(1, 0.85, 0.2)
            self.rect(mx + r.x / MAP_W * mw, my + mh - r.y / MAP_H * mh, 2.5, 2.5)
        for e in g.ents:
            Color(*TEAM[e.team])
            s = 6 if e.b else 3.2
            self.rect(mx + e.x / MAP_W * mw - s / 2, my + mh - e.y / MAP_H * mh - s / 2, s, s)
        vw, vh = self.view_world()
        Color(1, 1, 1)
        Line(rectangle=(mx + g.cam[0] / MAP_W * mw, my + mh - (g.cam[1] + vh) / MAP_H * mh, vw / MAP_W * mw, vh / MAP_H * mh), width=1.3)

    # ---- tactile
    def in_mm(self, x, y):
        mx, my, mw, mh = self.mm_rect()
        return mx <= x <= mx + mw and my <= y <= my + mh

    def mm_jump(self, x, y):
        mx, my, mw, mh = self.mm_rect()
        vw, vh = self.view_world()
        self.g.cam[0] = (x - mx) / mw * MAP_W - vw / 2
        self.g.cam[1] = (my + mh - y) / mh * MAP_H - vh / 2
        self.g.note('minimap')

    def on_touch_down(self, t):
        if not self.collide_point(*t.pos):
            return False
        self.touches[t.uid] = (t.x, t.y)
        if len(self.touches) >= 2:
            pts = list(self.touches.values())[:2]
            self.pinch0 = (math.hypot(pts[0][0] - pts[1][0], pts[0][1] - pts[1][1]) or 1, self.zoom)
            self.pinching = True
            self.start = None
            return True
        if self.in_mm(t.x, t.y):
            self.mm_drag = True
            self.mm_jump(t.x, t.y)
            return True
        self.start = self.cur = (t.x, t.y)
        self.moved = False
        self.dbl = bool(getattr(t, 'is_double_tap', False))
        if self.g.placing:
            self.ghost = self.s2w(t.x, t.y)
        return True

    def on_touch_move(self, t):
        if t.uid not in self.touches:
            return False
        self.touches[t.uid] = (t.x, t.y)
        if self.pinching:
            if len(self.touches) >= 2 and self.pinch0:
                pts = list(self.touches.values())[:2]
                d = math.hypot(pts[0][0] - pts[1][0], pts[0][1] - pts[1][1]) or 1
                self.zoom = max(0.6, min(1.8, self.pinch0[1] * d / self.pinch0[0]))
                self.g.note('zoom')
            return True
        if self.mm_drag:
            self.mm_jump(t.x, t.y)
            return True
        if not self.start:
            return False
        if math.hypot(t.x - self.start[0], t.y - self.start[1]) > dp(12):
            self.moved = True
        self.cur = (t.x, t.y)
        if self.g.placing:
            self.ghost = self.s2w(t.x, t.y)
        elif not self.rect_mode and self.moved:
            self.g.cam[0] -= t.dx / self.sc
            self.g.cam[1] += t.dy / self.sc
            self.g.note('pan')
        return True

    def on_touch_up(self, t):
        if t.uid not in self.touches:
            return False
        del self.touches[t.uid]
        if self.pinching:
            if not self.touches:
                self.pinching = False
            return True
        self.mm_drag = False
        if not self.start:
            return False
        g = self.g
        start, self.start = self.start, None
        if g.placing:
            return True
        if self.rect_mode and self.moved:
            x0, y0 = self.s2w(*start)
            x1, y1 = self.s2w(t.x, t.y)
            g.select_rect(x0, y0, x1, y1)
            self.rect_mode = False
            return True
        if self.moved:
            return True
        wx, wy = self.s2w(t.x, t.y)
        hit = g.pick(wx, wy)
        own = [e for e in g.sel if e.team == g.me]
        if hit and hit.team == g.me:
            if self.dbl and not hit.b:
                vw, vh = self.view_world()
                g.select_kind(hit.kind, g.cam[0], g.cam[1], g.cam[0] + vw, g.cam[1] + vh)
            else:
                g.sel = [hit]
            g.note_sel()
        elif own:
            g.command(wx, wy)
        else:
            g.sel = [hit] if hit else []
            g.note_sel()
        return True


# ------------------------------------------------------------------ pages (reprises de la V5)
class SkirmishPage(Page):
    def __init__(self, app, **kw):
        super().__init__(app, 'skirmish', **kw)
        sk = app.sk
        box = panel()
        box.add_widget(lbl('[b]Escarmouche[/b]', 22, size_hint=(1, None), height=dp(28)))
        box.add_widget(lbl('Votre faction', 12, color=(1, .88, .5, 1), halign='left', size_hint=(1, None), height=dp(16)))
        box.add_widget(FacRow(sk['me'], lambda f: sk.update(me=f), size_hint=(1, 1)))
        box.add_widget(lbl('Faction adverse (IA)', 12, color=(1, .88, .5, 1), halign='left', size_hint=(1, None), height=dp(16)))
        box.add_widget(FacRow(sk['foe'], lambda f: sk.update(foe=f), size_hint=(1, 1)))
        box.add_widget(lbl('Difficulté', 12, color=(1, .88, .5, 1), halign='left', size_hint=(1, None), height=dp(16)))
        box.add_widget(ChoiceRow([(0, 'Facile'), (1, 'Normal'), (2, 'Difficile')], sk['diff'],
                                 lambda v: sk.update(diff=v), size_hint=(1, None), height=dp(40)))
        box.add_widget(nav(app, 'menu', 'Jouer', app.start_skirmish))
        self.root_f.add_widget(box)


class MPPage(Page):
    def __init__(self, app, **kw):
        super().__init__(app, 'mp', **kw)
        box = panel((.9, .9))
        box.add_widget(lbl('[b]Multijoueur : téléphone à téléphone[/b]', 21, size_hint=(1, None), height=dp(30)))
        box.add_widget(lbl("Les deux téléphones doivent être sur le [b]même Wi-Fi[/b], ou l'un des deux partage sa connexion "
                           "(point d'accès) à l'autre.\nL'un crée la partie et lit son adresse, l'autre la saisit pour rejoindre.",
                           12, color=(.88, .93, 1, 1), size_hint=(1, .38)))
        row = BoxLayout(spacing=dp(12), size_hint=(1, .5))
        b1 = BigBtn('Créer une partie', 'i_home', "Vous êtes l'hôte", size=17)
        b1.bind(on_release=lambda *_: app.go('host'))
        b2 = BigBtn('Rejoindre', 'i_net', "Saisir l'adresse de l'hôte", size=17)
        b2.bind(on_release=lambda *_: app.go('join'))
        row.add_widget(b1)
        row.add_widget(b2)
        box.add_widget(row)
        box.add_widget(nav(app, 'menu'))
        self.root_f.add_widget(box)


class HostPage(Page):
    def __init__(self, app, **kw):
        super().__init__(app, 'host', **kw)
        box = panel()
        box.add_widget(lbl('[b]Créer une partie[/b]', 21, size_hint=(1, None), height=dp(28)))
        self.ip = lbl('', 17, color=(.6, 1, .7, 1), size_hint=(1, None), height=dp(30))
        self.status = lbl('', 13, color=(1, .92, .6, 1), size_hint=(1, None), height=dp(22))
        box.add_widget(self.ip)
        box.add_widget(self.status)
        box.add_widget(lbl('Votre faction', 12, color=(1, .88, .5, 1), halign='left', size_hint=(1, None), height=dp(16)))
        box.add_widget(FacRow(app.mp['me'], lambda f: app.mp.update(me=f), size_hint=(1, 1)))
        row = BoxLayout(size_hint=(1, None), height=dp(46), spacing=dp(10))
        b = BigBtn('Retour', 'i_home', size=15)
        b.bind(on_release=lambda *_: app.go('mp'))
        self.start = BigBtn('Lancer la partie', 'i_play', style='ui_btn_bad', size=15)
        self.start.bind(on_release=lambda *_: app.start_host_game())
        row.add_widget(b)
        row.add_widget(self.start)
        box.add_widget(row)
        self.root_f.add_widget(box)

    def on_enter(self, *a):
        app = self.app
        app.close_lobby()
        app.srv = net.Server()
        app.guest_fac = None
        self.ip.text = "Votre adresse : [b]%s[/b]   (port %d)" % (net.local_ip(), net.PORT)
        self.status.text = "En attente d'un joueur…"
        self.ev = Clock.schedule_interval(self.poll, 0.3)

    def on_leave(self, *a):
        if getattr(self, 'ev', None):
            self.ev.cancel()
        if self.app.sm.current != 'game':
            self.app.close_lobby()

    def poll(self, dt):
        app = self.app
        s = app.srv
        if s is None:
            return
        if s.error:
            self.status.text = 'Erreur : ' + str(s.error)
            return
        if s.peer:
            for m in s.peer.poll():
                if m['k'] == 'hello':
                    app.guest_fac = m['fac']
            if not s.peer.alive:
                self.status.text = 'Le joueur a quitté. En attente d\'un joueur…'
                app.guest_fac = None
                s.peer.close()
                app.srv.close()
                app.srv = net.Server()
                return
            if app.guest_fac:
                self.status.text = 'Joueur connecté (%s) : vous pouvez lancer !' % FACTIONS[app.guest_fac]['short']
                self.start.set_style('ui_btn_on')
            else:
                self.status.text = 'Joueur connecté…'
        else:
            self.start.set_style('ui_btn_bad')


class JoinPage(Page):
    def __init__(self, app, **kw):
        super().__init__(app, 'join', **kw)
        box = panel()
        box.add_widget(lbl('[b]Rejoindre une partie[/b]', 21, size_hint=(1, None), height=dp(28)))
        row = BoxLayout(size_hint=(1, None), height=dp(44), spacing=dp(8))
        self.ip = TextInput(hint_text="Adresse de l'hôte, ex : 192.168.1.23", multiline=False, font_size=dp(17),
                            input_filter=lambda s, undo: ''.join(c for c in s if c in '0123456789.'),
                            write_tab=False, size_hint=(.65, 1))
        self.go_btn = BigBtn('Se connecter', 'i_net', size=14, style='ui_btn_on', size_hint=(.35, 1))
        self.go_btn.bind(on_release=lambda *_: self.connect())
        row.add_widget(self.ip)
        row.add_widget(self.go_btn)
        box.add_widget(row)
        self.status = lbl('', 13, color=(1, .92, .6, 1), size_hint=(1, None), height=dp(22))
        box.add_widget(self.status)
        box.add_widget(lbl('Votre faction', 12, color=(1, .88, .5, 1), halign='left', size_hint=(1, None), height=dp(16)))
        box.add_widget(FacRow(app.mp['me2'], lambda f: app.mp.update(me2=f), size_hint=(1, 1)))
        box.add_widget(nav(app, 'mp'))
        self.root_f.add_widget(box)
        self.conn = None

    def connect(self):
        ip = self.ip.text.strip()
        if not ip:
            self.status.text = "Saisissez l'adresse affichée sur le téléphone de l'hôte."
            return
        self.status.text = 'Connexion…'
        self.conn = net.Connector(ip)

    def on_enter(self, *a):
        self.status.text = ''
        self.conn = None
        self.ev = Clock.schedule_interval(self.poll, 0.25)

    def on_leave(self, *a):
        if getattr(self, 'ev', None):
            self.ev.cancel()
        if self.app.sm.current != 'game':
            self.app.close_lobby()

    def poll(self, dt):
        app = self.app
        c = self.conn
        if c and c.done and not app.cli_peer:
            if c.error:
                self.status.text = 'Échec : ' + str(c.error)
                self.conn = None
            else:
                app.cli_peer = c.peer
                c.peer.send({'k': 'hello', 'fac': app.mp['me2']})
                self.status.text = "Connecté ! En attente du lancement par l'hôte…"
        if app.cli_peer:
            for m in app.cli_peer.poll():
                if m['k'] == 'start':
                    app.start_client_game(m['init'])
                    return
            if not app.cli_peer.alive:
                self.status.text = "L'hôte a fermé la partie."
                app.cli_peer = None
                self.conn = None




# ------------------------------------------------------------------ pages V6
class MenuPage(Page):
    def __init__(self, app, **kw):
        super().__init__(app, 'menu', **kw)
        r = self.root_f
        r.add_widget(Pic('logo', size_hint=(None, None), size=(dp(470), dp(133)), pos_hint={'center_x': .5, 'top': .98}))
        r.add_widget(lbl('Trois peuples • Tutoriels • Campagnes • Escarmouche • Duel entre téléphones', 12,
                         color=(.92, .95, 1, 1), size_hint=(1, None), height=dp(22), pos_hint={'center_x': .5, 'top': .66}))
        row = BoxLayout(spacing=dp(14), size_hint=(.9, None), height=dp(112), pos_hint={'center_x': .5, 'center_y': .38})
        for text, icon, sub, page in (("Escarmouche", 'i_army', "Partie rapide contre l'IA", 'skirmish'),
                                      ("Multijoueur", 'i_net', "Duel de téléphone à téléphone", 'mp'),
                                      ("Campagne", 'i_book', "3 peuples • tutoriels • 18 missions", 'campaign')):
            b = BigBtn(text, icon, sub, size=19)
            b.bind(on_release=lambda *_, p=page: (app.snd.play('sfx_click'), app.go(p)))
            row.add_widget(b)
        r.add_widget(row)
        row2 = BoxLayout(spacing=dp(12), size_hint=(.5, None), height=dp(44), pos_hint={'center_x': .5, 'y': .05})
        b1 = BigBtn('Réglages', 'i_hammer' if 'i_hammer' in DATA else None, size=14)
        b1.bind(on_release=lambda *_: app.go('settings'))
        b2 = BigBtn("Revoir l'intro", 'i_play', size=14)
        b2.bind(on_release=lambda *_: app.go('intro'))
        row2.add_widget(b1)
        row2.add_widget(b2)
        r.add_widget(row2)


class CampaignPage(Page):
    def __init__(self, app, **kw):
        super().__init__(app, 'campaign', **kw)
        self.box = panel()
        self.root_f.add_widget(self.box)

    def on_pre_enter(self, *a):
        app = self.app
        self.box.clear_widgets()
        self.box.add_widget(lbl('[b]Campagne[/b]', 22, size_hint=(1, None), height=dp(28)))
        self.box.add_widget(lbl('Chaque peuple a son tutoriel guidé puis 6 missions. Commencez par le tutoriel !', 12,
                                color=(.88, .93, 1, 1), size_hint=(1, None), height=dp(20)))
        row = BoxLayout(spacing=dp(8), size_hint=(1, 1))
        for fac, camp in campaign.CAMPAIGNS.items():
            n = campaign.count_done(app.done, fac)
            card = FacCard(fac, '\n[b]%s[/b]\nProgression : %d/%d' % (camp['title'], n, campaign.NMISSIONS))
            card.bind(on_release=lambda *_, f=fac: app.open_missions(f))
            row.add_widget(card)
        self.box.add_widget(row)
        self.box.add_widget(nav(app, 'menu'))


class MissionsPage(Page):
    def __init__(self, app, **kw):
        super().__init__(app, 'missions', **kw)
        self.box = panel()
        self.root_f.add_widget(self.box)
        self.fac, self.idx = 'kingdom', 0

    def show(self, fac, idx=None):
        app = self.app
        self.fac = fac
        camp = campaign.CAMPAIGNS[fac]
        if idx is None:
            idx = next((i for i in range(campaign.NMISSIONS) if ('%s:%d' % (fac, i)) not in app.done), campaign.NMISSIONS - 1)
        self.idx = idx
        self.box.clear_widgets()
        self.box.add_widget(lbl('[b]%s[/b] : %s' % (FACTIONS[fac]['name'], camp['title']), 18, size_hint=(1, None), height=dp(28)))
        body = BoxLayout(spacing=dp(8))
        sv = ScrollView(size_hint=(.42, 1), do_scroll_x=False, bar_width=dp(4))
        left = BoxLayout(orientation='vertical', spacing=dp(5), size_hint_y=None)
        left.bind(minimum_height=left.setter('height'))
        for i, m in enumerate(camp['missions']):
            done = ('%s:%d' % (fac, i)) in app.done
            ok = campaign.unlocked(app.done, fac, i)
            title = ('Tutoriel : ' if m.get('tutorial') else '%d. ' % i) + m['title']
            b = BigBtn(title, 'i_star' if done else ('i_lock' if not ok else ('i_book' if m.get('tutorial') else 'i_amove')),
                       'Terminée' if done else ('Verrouillée' if not ok else 'Disponible'),
                       style='ui_btn_on' if i == idx else 'ui_btn', size=12, size_hint_y=None, height=dp(50))
            if not ok:
                b.opacity = .6
            b.bind(on_release=lambda *_, k=i: self.show(fac, k))
            left.add_widget(b)
        sv.add_widget(left)
        right = BoxLayout(orientation='vertical', padding=dp(8), size_hint=(.58, 1))
        attach_bg(right, 'ui_card', 20)
        m = camp['missions'][idx]
        objs = '\n'.join('• ' + o for o in campaign.objectives_preview(fac, idx))
        text = '[b]%s[/b]\n\n%s\n\n[color=ffd870][b]Objectifs[/b][/color]\n%s\n\nAdversaire : %s' % (
            m['title'], m['brief'], objs, FACTIONS[m['enemy']]['name'])
        if idx == 0:
            text = '[i]%s[/i]\n\n' % camp['intro'] + text
        right.add_widget(lbl(text, 11, halign='left', valign='top'))
        body.add_widget(sv)
        body.add_widget(right)
        self.box.add_widget(body)
        ok = campaign.unlocked(app.done, fac, idx)
        self.box.add_widget(nav(app, 'campaign', 'Lancer la mission' if ok else 'Verrouillée',
                                (lambda: app.start_mission(fac, idx)) if ok else (lambda: None),
                                'ui_btn_on' if ok else 'ui_btn_bad'))


class SettingsPage(Page):
    def __init__(self, app, **kw):
        super().__init__(app, 'settings', **kw)
        self.box = panel((.9, .94))
        self.root_f.add_widget(self.box)

    def on_pre_enter(self, *a):
        app, st = self.app, self.app.settings
        self.box.clear_widgets()
        self.box.add_widget(lbl('[b]Réglages[/b]', 22, size_hint=(1, None), height=dp(28)))
        rows = (('Effets sonores', 'sound', [(True, 'Activés'), (False, 'Coupés')]),
                ('Musique', 'music', [(True, 'Activée'), (False, 'Coupée')]),
                ('Qualité graphique', 'quality', [(1, 'Élevée'), (0, 'Réduite (plus fluide)')]),
                ("Afficher les images/s", 'fps', [(True, 'Oui'), (False, 'Non')]))
        for title, key, opts in rows:
            r = BoxLayout(size_hint=(1, None), height=dp(40), spacing=dp(8))
            r.add_widget(lbl(title, 13, True, halign='left', size_hint=(.34, 1)))
            r.add_widget(ChoiceRow(opts, st[key], lambda v, k=key: app.set_option(k, v), size_hint=(.66, 1)))
            self.box.add_widget(r)
        log = ''
        try:
            with open(os.path.join(app.user_data_dir, 'crash.log')) as f:
                log = f.read()[-420:]
        except Exception:
            pass
        self.box.add_widget(lbl('[b]Journal technique[/b]  (utile pour signaler un bug)\n' + (log.replace('[', '(').replace(']', ')') or 'Aucune erreur enregistrée.'),
                                10, color=(.85, .9, 1, 1), halign='left', valign='top', size_hint=(1, 1)))
        self.box.add_widget(nav(app, 'menu'))


# ------------------------------------------------------------------ introduction animée
class IntroView(FloatLayout):
    DUR = 27.0

    def __init__(self, app, **kw):
        super().__init__(**kw)
        self.app, self.t, self.ev = app, 0.0, None
        self.cap = lbl('', 19, True, color=(1, .95, .85, 1), size_hint=(.84, None), height=dp(64), pos_hint={'center_x': .5, 'y': .05})
        self.fac = lbl('', 28, True, color=(1, .9, .6, 1), size_hint=(.8, None), height=dp(44), pos_hint={'center_x': .5, 'top': .93})
        self.emb = Pic(None, size_hint=(None, None), size=(dp(70), dp(70)), pos_hint={'center_x': .5, 'top': .80})
        self.logo = Pic('logo', size_hint=(None, None), size=(dp(560), dp(158)), pos_hint={'center_x': .5, 'center_y': .58})
        self.tap = lbl('Touchez pour commencer', 17, True, color=(1, .95, .8, 1), size_hint=(.6, None), height=dp(30), pos_hint={'center_x': .5, 'y': .12})
        self.hint = lbl('Touchez pour passer', 10, color=(1, 1, 1, .6), size_hint=(.3, None), height=dp(18), pos_hint={'right': .99, 'y': .005})
        for w in (self.emb, self.logo, self.cap, self.fac, self.tap, self.hint):
            self.add_widget(w)
        self.logo.opacity = self.tap.opacity = self.emb.opacity = 0

    def start(self):
        self.t = 0.0
        self.app.snd.music('music_intro', loop=False, vol=.85)
        self.ev = Clock.schedule_interval(self.tick, 1 / 30)

    def stop(self):
        if self.ev:
            self.ev.cancel()
            self.ev = None

    def finish(self):
        self.stop()
        self.app.settings.set('intro', False)
        self.app.go('menu')

    def on_touch_down(self, t):
        if self.t > 15.5 or self.t > 3:
            self.finish()
        else:
            self.t = max(self.t, 3.0)
        return True

    # -- utilitaires
    def blit(self, name, x, y, w, h, flip=False, col=(1, 1, 1, 1)):
        Color(*col)
        if flip:
            Rectangle(texture=tex(name), pos=(x, y), size=(w, h), tex_coords=(1, 0, 0, 0, 0, 1, 1, 1))
        else:
            Rectangle(texture=tex(name), pos=(x, y), size=(w, h))

    def unit(self, fac, kind, team, cx, fy, sf, flip, pose):
        m = UNIT_META[kind]
        x = cx - (m['ax'] if not flip else m['w'] - m['ax']) * sf
        self.blit('u_%s_%s_%d_%s' % (fac, kind, team, pose), x, fy - m['foot'] * sf, m['w'] * sf, m['h'] * sf, flip=flip)

    def ease(self, a, b, t):
        k = max(0.0, min(1.0, (t - a) / (b - a)))
        return k * k * (3 - 2 * k)

    def fade(self, t, a, b, c, d):
        return max(0.0, min(1.0, (t - a) / max(.01, b - a))) * max(0.0, min(1.0, (d - t) / max(.01, d - c)))

    def tick(self, dt):
        self.t += dt
        t = self.t
        if t > self.DUR:
            self.finish()
            return
        try:
            self.paint(t)
        except Exception:
            log_error('intro')
        # textes
        caps = ((1.2, 5.6, "Il fut un temps où trois peuples se disputaient le monde…"),
                (11.0, 14.6, "Le fracas des armes annonça l'aube d'une nouvelle ère."),
                (17.5, 22.5, "Choisissez votre peuple. Écrivez la légende."))
        txt, a = '', 0
        for s, e, c in caps:
            if s <= t <= e:
                txt, a = c, self.fade(t, s, s + .9, e - .9, e)
        self.cap.text, self.cap.opacity = txt, a
        names = ((6.0, 7.5, 'kingdom'), (7.5, 9.0, 'horde'), (9.0, 10.6, 'sylvan'))
        ft, fo = '', 0
        for s, e, fc in names:
            if s <= t < e:
                ft, fo = FACTIONS[fc]['name'], self.fade(t, s, s + .35, e - .35, e)
                self.emb.set('em_' + fc)
                self.emb.opacity = fo
        self.fac.text, self.fac.opacity = ft, fo
        if not ft:
            self.emb.opacity = 0
        lk = self.ease(15.0, 16.6, t)
        self.logo.opacity = lk
        self.logo.size = (dp(560) * (.72 + .28 * lk), dp(158) * (.72 + .28 * lk))
        self.tap.opacity = (.55 + .45 * math.sin(t * 4)) if t > 19.5 else 0
        self.hint.opacity = .6 if t < 15 else 0

    def paint(self, t):
        W, H = max(1.0, self.width), max(1.0, self.height)
        S = H / 640.0
        c = self.canvas.before
        c.clear()
        with c:
            Color(0, 0, 0, 1)
            Rectangle(pos=(0, 0), size=(W, H))
            if t < 15.2:
                self.scene(t, W, H, S)
            else:
                self.finale(t, W, H, S)
            fb = 1 - self.ease(0, 1.4, t)
            if fb > 0:
                Color(0, 0, 0, fb)
                Rectangle(pos=(0, 0), size=(W, H))
            if 14.4 < t < 16.2:                                   # éclair blanc au moment du titre
                a = self.ease(14.4, 15.0, t) * (1 - self.ease(15.0, 16.2, t))
                Color(1, .95, .85, a)
                Rectangle(pos=(0, 0), size=(W, H))

    def scene(self, t, W, H, S):
        shake = 0.0
        if 11 < t < 15:
            shake = math.sin(t * 40) * 3 * S * min(1, (t - 11) / 2)
        ox = shake
        self.blit('sky', 0, 0, W, H)
        rise = self.ease(0, 9, t)
        sx_, sy_ = W * .62, H * (.30 + .24 * rise)
        self.blit('light_warm', sx_ - H * .7, sy_ - H * .7, H * 1.4, H * 1.4, col=(1, 1, 1, .9))
        self.blit('sparkle', sx_ - 26 * S, sy_ - 26 * S, 52 * S, 52 * S, col=(1, 1, 1, .9))
        for k in range(4):
            PushMatrix()
            Rotate(angle=-20 + k * 13 + math.sin(t * .3) * 4, origin=(sx_, sy_))
            self.blit('ray', sx_ - 40 * S, sy_ - 20 * S, 80 * S, H * .9, col=(1, 1, 1, .22))
            PopMatrix()
        pan = t * 6 * S
        self.blit('mtn_far', -W * .1 - pan * .2 + ox, H * .26, W * 1.3, H * .36)
        self.blit('mtn_mid', -W * .1 - pan * .45 + ox, H * .17, W * 1.3, H * .36)
        for i, (cy, spd, sz, al) in enumerate(((.78, 7, 1.0, .85), (.66, 11, .75, .7), (.85, 5, 1.2, .6))):
            cx = (W * 1.2 - (t * spd * S + i * W * .45)) % (W * 1.5) - W * .2
            self.blit('cloud', cx, H * cy, 256 * sz * S * 1.2, 96 * sz * S * 1.2, col=(1, 1, 1, al))
        for i in range(5):
            bx = (W * 1.1 - ((t * (40 + i * 7) + i * 130) * S)) % (W * 1.3) - W * .1
            by = H * (.62 + .05 * i) + math.sin(t * 2 + i) * 10 * S
            self.blit('bird_%d' % (int(t * 5 + i) % 2), bx, by, 40 * S, 20 * S)
        self.blit('hills', -W * .1 - pan * .8 + ox, H * .08, W * 1.3, H * .32)
        gh = H * .20
        T = dp(210)
        Color(1, 1, 1, 1)
        off = pan * 1.6 / T
        Rectangle(texture=tex('grass'), pos=(0, 0), size=(W, gh), tex_coords=(off, 0, off + W / T, 0, off + W / T, gh / T, off, gh / T))
        Color(0, 0, 0, .25)
        Rectangle(pos=(0, 0), size=(W, gh))
        fy = H * .09
        sf = H * 0.0033
        if t < 5.5:
            return
        a_t = t - 5.5
        wk = lambda i: 'walk1' if int(t * 5.5 + i) % 2 == 0 else 'walk2'
        atk = lambda i: 'atk' if int(t * 4 + i) % 2 == 0 else 'idle'
        # --- armée du Royaume (gauche), de la Horde (droite), de la Sylve (fond)
        Lk = [('soldier', 0), ('archer', 1), ('soldier', 2), ('knight', 3), ('heavy', 4), ('healer', 5)]
        Rh = [('soldier', 0), ('knight', 1), ('heavy', 2), ('archer', 3), ('soldier', 4), ('healer', 5)]
        Sv = [('archer', 0), ('soldier', 1), ('heavy', 2), ('knight', 3), ('archer', 4)]
        clash = self.ease(10.0, 11.4, t)
        meet = W * (.5 - .035 * math.sin(t * 3) * clash)
        for i, (k, o) in enumerate(Lk):
            base = -W * .25 + (W * .50 - 0 * i) * self.ease(5.6, 10.8, t)
            x = base - (i % 3) * 38 * S - (i // 3) * 60 * S + W * .04 * (1 - clash * 0)
            x = min(x, meet - 30 * S - (i % 3) * 30 * S)
            y = fy + (i % 3) * H * .02
            self.unit('kingdom', k, 0, x, y, sf * (1 - (i % 3) * .06), False, atk(i) if t > 10.6 else wk(i))
        for i, (k, o) in enumerate(Rh):
            base = W * 1.25 - (W * .50) * self.ease(6.4, 10.8, t)
            x = base + (i % 3) * 38 * S + (i // 3) * 60 * S
            x = max(x, meet + 30 * S + (i % 3) * 30 * S)
            y = fy + (i % 3) * H * .02
            self.unit('horde', k, 1, x, y, sf * (1 - (i % 3) * .06), True, atk(i + 1) if t > 10.6 else wk(i))
        if t > 8.4:
            for i, (k, o) in enumerate(Sv):
                prog = self.ease(8.4, 12.5, t)
                x = W * (.34 + .08 * i) + math.sin(i * 2) * 10 * S
                y = fy + H * (.16 - .11 * prog)
                sc2 = sf * (.45 + .5 * prog)
                self.unit('sylvan', k, 0, x, y, sc2, False, atk(i + 2) if t > 11.5 else wk(i))
        if t > 10.8:                                         # projectiles, poussière, étincelles
            for j in range(9):
                ph = (t * 1.6 + j * .37) % 1.0
                typ = j % 3
                if typ == 0:
                    x0, x1, nm = W * .30, W * .62, 'arrow'
                elif typ == 1:
                    x0, x1, nm = W * .72, W * .40, 'proj_bolt'
                else:
                    x0, x1, nm = W * .40, W * .70, 'proj_orb'
                px = x0 + (x1 - x0) * ph
                py = fy + H * .20 + math.sin(ph * 3.14) * H * .12 + (j % 4) * H * .01
                w_, h_ = (36, 8) if nm != 'proj_orb' else (30, 30)
                self.blit(nm, px - w_ * S / 2, py, w_ * S * 1.4, h_ * S * 1.4, flip=(typ == 1))
            for j in range(10):
                ph = (t * .9 + j * .21) % 1.0
                self.blit('puff', meet + (j - 5) * 18 * S, fy + ph * 30 * S, (26 + ph * 40) * S, (26 + ph * 40) * S, col=(.75, .65, .5, (1 - ph) * .5))
            for j in range(4):
                ph = (t * 3 + j * .5) % 1.0
                self.blit('sparkle', meet + (j - 2) * 34 * S, fy + H * .06 + (j % 2) * 20 * S, 40 * S * ph, 40 * S * ph, col=(1, 1, .8, 1 - ph))

    def finale(self, t, W, H, S):
        Color(.03, .02, .06, 1)
        Rectangle(pos=(0, 0), size=(W, H))
        self.blit('light_warm', W / 2 - H * .9, H * .58 - H * .9, H * 1.8, H * 1.8, col=(1, .8, .5, .7))
        for k in range(10):
            PushMatrix()
            Rotate(angle=k * 36 + t * 6, origin=(W / 2, H * .58))
            self.blit('ray', W / 2 - 50 * S, H * .58, 100 * S, H * .85, col=(1, .85, .5, .16))
            PopMatrix()
        for i in range(46):
            ph = (t * .22 + i * .137) % 1.0
            x = W * ((i * .6180339) % 1.0) + math.sin(ph * 9 + i) * 14 * S
            y = ph * H * 1.05
            sz = (6 + (i % 4) * 3) * S
            self.blit('sparkle', x - sz / 2, y - sz / 2, sz, sz, col=(1, .75 + .2 * math.sin(i), .4, math.sin(ph * 3.14) * .9))
        for i, fc in enumerate(('kingdom', 'horde', 'sylvan')):
            e = self.ease(16.8 + i * .5, 17.8 + i * .5, t)
            self.blit('em_' + fc, W * (.28 + .22 * i) - 36 * S, H * .24, 72 * S, 72 * S, col=(1, 1, 1, e))
        vg = self.ease(15, 17, t)
        self.blit('vignette', 0, 0, W, H, col=(1, 1, 1, .8 * vg))


class IntroPage(Screen):
    def __init__(self, app, **kw):
        super().__init__(name='intro', **kw)
        self.view = IntroView(app)
        self.add_widget(self.view)

    def on_enter(self, *a):
        self.view.start()

    def on_leave(self, *a):
        self.view.stop()


# ------------------------------------------------------------------ application
def copy_setup(s):
    import copy
    return copy.deepcopy(s)


class RTSApp(App):
    def build(self):
        global APP
        APP = self
        self.last_error = ''
        try:
            ExceptionManager.add_handler(_Handler())
        except Exception:
            pass
        self.settings = Settings(os.path.join(self.user_data_dir, 'settings.json'))
        self.snd = Snd(os.path.join(self.user_data_dir, 'snd'), self.settings)
        self.g = Game()
        self.sk = dict(me='kingdom', foe='horde', diff=1)
        self.mp = dict(me='kingdom', me2='sylvan')
        self.srv = None
        self.cli_peer = None
        self.guest_fac = None
        self.mode = 'skirmish'
        self.cur_fac, self.cur_idx = 'kingdom', 0
        self.leave_t = 0
        self.prog_path = os.path.join(self.user_data_dir, 'progress.json')
        self.done = campaign.load(self.prog_path)
        self.sm = ScreenManager(transition=FadeTransition(duration=0.18))
        self.sm.add_widget(MenuPage(self))
        self.sm.add_widget(SkirmishPage(self))
        self.sm.add_widget(MPPage(self))
        self.sm.add_widget(HostPage(self))
        self.sm.add_widget(JoinPage(self))
        self.sm.add_widget(CampaignPage(self))
        self.missions = MissionsPage(self)
        self.sm.add_widget(self.missions)
        self.sm.add_widget(SettingsPage(self))
        self.sm.add_widget(IntroPage(self))
        self.sm.add_widget(self.build_game_screen())
        self.sm.bind(current=self.on_screen)
        Window.bind(on_keyboard=self.on_key)
        Clock.schedule_interval(self.tick_fps, 0.5)
        self.sm.current = 'intro' if self.settings['intro'] else 'menu'
        if self.sm.current == 'menu':
            self.snd.music('music_menu', True, .5)
        return self.sm

    def on_pause(self):
        return True

    def on_screen(self, sm, name):
        if name in ('menu', 'skirmish', 'mp', 'host', 'join', 'campaign', 'missions', 'settings'):
            apply_skin(None)
            self.snd.music('music_menu', True, .5)
        elif name == 'game':
            self.snd.music('music_battle', True, .45)

    def set_option(self, key, val):
        self.settings.set(key, val)
        if key == 'music':
            if val:
                self.snd.music('music_menu', True, .5)
            else:
                self.snd.stop_music()

    def tick_fps(self, dt):
        self.fps_lab.opacity = 1 if (self.settings['fps'] and self.sm.current == 'game') else 0
        if self.fps_lab.opacity:
            err = ('  ! ' + self.last_error[:50]) if self.last_error else ''
            self.fps_lab.text = '%d i/s%s' % (Clock.get_fps(), err)

    # ---- navigation
    def go(self, name):
        self.sm.current = name

    def on_key(self, window, key, *a):
        if key != 27:
            return False
        cur = self.sm.current
        if cur == 'game':
            self.press_menu()
            return True
        if cur == 'intro':
            self.sm.get_screen('intro').view.finish()
            return True
        if cur == 'menu':
            return False
        back = {'skirmish': 'menu', 'mp': 'menu', 'host': 'mp', 'join': 'mp', 'campaign': 'menu', 'missions': 'campaign', 'settings': 'menu'}
        self.go(back.get(cur, 'menu'))
        return True

    def open_missions(self, fac):
        self.missions.show(fac)
        self.go('missions')

    # ---- démarrage des parties
    def begin_game(self, mode):
        self.mode = mode
        g, v = self.g, self.view
        apply_skin(g.fac[g.me])
        v.zoom, v.need_center, v.rect_mode, v.ghost, v.rings, v.over_done = 1.0, True, False, None, [], False
        v.make_decor()
        g.paused = False
        self.sig = None
        self.leave_t = 0
        self.go('game')

    def start_skirmish(self):
        g = self.g
        g.diff = self.sk['diff']
        g.reset(self.sk['me'], self.sk['foe'], seed=random.randint(1, 10 ** 6), ai_teams=(1,))
        self.view.net = None
        self.begin_game('skirmish')

    def start_mission(self, fac, idx):
        m = campaign.CAMPAIGNS[fac]['missions'][idx]
        g = self.g
        g.diff = m['diff']
        g.reset(fac, m['enemy'], setup=campaign.mission_setup(fac, idx), seed=m['seed'],
                ai_teams=() if m.get('passive') else (1,))
        self.cur_fac, self.cur_idx = fac, idx
        self.view.net = None
        self.begin_game('campaign')

    def start_host_game(self):
        s = self.srv
        if not (s and s.peer and s.peer.alive and self.guest_fac):
            self.say_lobby("Attendez qu'un joueur se connecte.")
            return
        g = self.g
        g.reset(self.mp['me'], self.guest_fac, seed=random.randint(1, 10 ** 6), ai_teams=(), me=0)
        g.record_fx = True
        s.peer.send({'k': 'start', 'init': g.make_init(1)})
        self.view.net = dict(role='host', peer=s.peer, t=0)
        s.close()
        self.srv = None
        self.begin_game('host')

    def start_client_game(self, init):
        self.g.init_remote(init)
        self.view.net = dict(role='client', peer=self.cli_peer, t=0)
        self.cli_peer = None
        self.begin_game('client')

    def say_lobby(self, text):
        self.sm.get_screen('host').status.text = text

    def close_lobby(self):
        if self.srv:
            try:
                if self.srv.peer:
                    self.srv.peer.close()
                self.srv.close()
            except Exception:
                pass
            self.srv = None
        if self.cli_peer:
            self.cli_peer.close()
            self.cli_peer = None

    def close_net(self):
        n = self.view.net
        if n:
            try:
                n['peer'].send({'k': 'bye'})
                n['peer'].close()
            except Exception:
                pass
            self.view.net = None

    def finish_game(self):
        g = self.g
        self.close_net()
        apply_skin(None)
        if self.mode == 'campaign':
            key = '%s:%d' % (self.cur_fac, self.cur_idx)
            nxt = self.cur_idx
            if g.winner == g.me:
                self.done.add(key)
                campaign.save(self.prog_path, self.done)
                nxt = min(campaign.NMISSIONS - 1, self.cur_idx + 1)
            self.missions.show(self.cur_fac, nxt)
            self.go('missions')
        else:
            self.go('menu')

    def press_menu(self):
        g = self.g
        now = time.time()
        if g.over or (self.leave_t and now - self.leave_t < 3):
            self.finish_game()
        else:
            self.leave_t = now
            g.say('Touchez encore « Menu » pour quitter la partie')

    # ---- écran de jeu
    def build_game_screen(self):
        scr = Screen(name='game')
        root = FloatLayout()
        self.view = GameView(self.g, self, size_hint=(1, 1))
        root.add_widget(self.view)
        hud = BoxLayout(size_hint=(None, None), size=(dp(330), dp(36)), pos_hint={'x': 0.004, 'top': 0.996}, padding=(dp(8), dp(3)), spacing=dp(3))
        attach_bg(hud, 'ui_panel', 16)
        self.hud = {}
        for key, icon in (('wood', 'i_wood'), ('ore', 'i_ore'), ('pop', 'i_pop')):
            hud.add_widget(Pic(icon, size_hint=(None, 1), width=dp(26)))
            lb = lbl('0', 16, True, size_hint=(1, 1), halign='left')
            hud.add_widget(lb)
            self.hud[key] = lb
        root.add_widget(hud)
        self.obj = lbl('', 12, halign='left', valign='top', padding=(dp(8), dp(4)), size_hint=(None, None), size=(dp(320), dp(30)),
                       pos_hint={'center_x': .5, 'top': .996})
        attach_bg(self.obj, 'ui_panel', 14)
        self.obj.opacity = 0
        root.add_widget(self.obj)
        self.tut = lbl('', 12, halign='left', valign='top', padding=(dp(10), dp(6)), size_hint=(None, None), size=(dp(520), dp(92)),
                       pos_hint={'center_x': .5, 'top': .996})
        attach_bg(self.tut, 'ui_panel', 16)
        self.tut.opacity = 0
        root.add_widget(self.tut)
        self.msg = lbl('', 13, True, color=(1, .92, .6, 1), size_hint=(None, None), size=(dp(440), dp(30)), pos_hint={'center_x': .5, 'top': .80})
        attach_bg(self.msg, 'ui_panel', 14)
        self.msg.opacity = 0
        root.add_widget(self.msg)
        self.fps_lab = lbl('', 10, color=(1, 1, 1, .85), halign='left', size_hint=(None, None), size=(dp(260), dp(16)), pos_hint={'x': .115, 'y': .20})
        self.fps_lab.opacity = 0
        root.add_widget(self.fps_lab)
        grid = GridLayout(cols=2, spacing=dp(4), size_hint=(None, None), size=(dp(108), dp(4 * 56 - 4)), pos_hint={'x': 0.004, 'center_y': 0.56})
        self.tb = {}
        for name, cap, icon, fn in (
                ('rect', 'Sélection', 'i_rect', self.toggle_rect),
                ('army', 'Armée', 'i_army', lambda: self.g.select_army()),
                ('idle', 'Inactifs', 'i_idle', lambda: self.g.select_idle_workers()),
                ('amove', 'Attaquer', 'i_amove', self.toggle_amove),
                ('stop', 'Stop', 'i_stop', lambda: self.g.stop_selected()),
                ('pause', 'Pause', 'i_pause', self.toggle_pause),
                ('menu', 'Menu', 'i_home', self.press_menu)):
            b = ToolBtn(icon, cap, size_hint=(None, None), size=(dp(52), dp(52)))
            b.bind(on_release=lambda *_, f=fn: (self.snd.play('sfx_click'), f()))
            self.tb[name] = b
            grid.add_widget(b)
        root.add_widget(grid)
        self.bar = BoxLayout(size_hint=(1, None), height=dp(94), spacing=dp(5), padding=(dp(6), dp(5)))
        attach_bg(self.bar, 'ui_panel', 20)
        root.add_widget(self.bar)
        self.portrait = Pic(None, pad=dp(2), size_hint=(None, 1), width=dp(74))
        self.info = lbl('', 11.5, halign='left', size_hint=(None, 1), width=dp(205))
        self.scroll = ScrollView(size_hint=(1, 1), do_scroll_y=False, bar_width=dp(3))
        self.cardbox = BoxLayout(size_hint_x=None, spacing=dp(4))
        self.cardbox.bind(minimum_width=self.cardbox.setter('width'))
        self.scroll.add_widget(self.cardbox)
        self.sig = None
        self.cards = []
        scr.add_widget(root)
        Clock.schedule_interval(self.refresh, 1 / 8)
        return scr

    def card_icon(self, a):
        g, me = self.g, self.g.me
        if a['kind'] == 'cancel':
            return 'i_cancel'
        if a.get('icon'):
            return a['icon']
        return 'ic_%s_%s_%d' % (g.fac[me], a['kind'], me)

    def press(self, f):
        self.snd.play('sfx_click')
        f()

    def refresh(self, dt):
        if self.sm.current != 'game':
            return
        g, v = self.g, self.view
        me = g.me
        st = g.stock[me]
        self.hud['wood'].text = str(st['wood'])
        self.hud['ore'].text = str(st['ore'])
        self.hud['pop'].text = f'{g.pop(me)}/{POP_MAX}'
        self.msg.text = g.msg
        self.msg.opacity = 1 if g.msg_t > 0 else 0
        # tutoriel / objectifs
        si = g.step_info() if self.mode == 'campaign' else None
        if si:
            i, n, title, text = si
            self.tut.text = '[b][color=ffd870]Étape %d/%d : %s[/color][/b]\n%s' % (i + 1, n, title, text)
            self.tut.opacity = 1
            self.obj.opacity = 0
        else:
            self.tut.opacity = 0
            lines = g.objective_lines() if (g.mission and self.mode == 'campaign') else []
            if lines:
                self.obj.text = '\n'.join(('[color=7dff7d](fait)[/color] ' if d else '• ') + t for t, d in lines)
                self.obj.size = (dp(330), dp(12) + dp(15) * len(lines))
                self.obj.opacity = 1
            else:
                self.obj.opacity = 0
        acts = g.actions()
        sig = (tuple(a['kind'] for a in acts), g.placing, g.over)
        sel = g.sel
        pk = None
        if len(sel) == 1:
            e = sel[0]
            pk = 'ic_%s_%s_%d' % (g.fac[e.team], e.kind, e.team)
            role = ROLE_F.get((g.fac[e.team], e.kind)) or ROLE[e.kind]
            line = f"[b][size=15sp]{e.d['label']}[/size][/b]{' [color=ff8080](ennemi)[/color]' if e.team != me else ''}\n"
            line += f"[color=cfd8ec]{role}[/color]\n"
            line += f"PV {int(e.hp)}/{e.maxhp}"
            if not e.b:
                if e.kind == 'healer':
                    line += f"   Soin {e.d.get('heal', 0)}/s   Armure {e.d.get('armor', 0)}"
                else:
                    line += f"   Dég {e.d['dmg']}   Port {e.d['rng']}   Arm {e.d.get('armor', 0)}"
            if e.b and not e.built:
                line += f"\nChantier : {int(100 * e.bt / e.d['time'])} %"
            elif e.b and e.res:
                t = g.tech(e.team, e.res[0])
                line += f"\nRecherche : {t['name']} {int(100 * e.res[1] / t['time'])} %"
            elif e.b and e.queue:
                line += '\nProduction : ' + ', '.join(g.ust[e.team][k]['label'] for k in e.queue)
            if e.kind == 'worker' and e.carry:
                line += f"\nPorte {e.carry} {'minerai' if e.ctype == 'ore' else 'bois'}"
        elif sel:
            ks = [x.kind for x in sel if not x.b]
            if ks:
                top = max(set(ks), key=ks.count)
                pk = 'ic_%s_%s_%d' % (g.fac[me], top, me)
                line = f'[b][size=15sp]{len(sel)} unités[/size][/b]\n' + ', '.join(f'{ks.count(k)} {g.ust[me][k]["label"]}' for k in dict.fromkeys(ks))
            else:
                line = f'{len(sel)} sélectionnés'
        else:
            line = '[b]Rien de sélectionné[/b]\nGlisser : caméra   Pincer : zoom\nToucher une unité pour la sélectionner'
        self.info.text = line
        self.portrait.set(pk)
        self.tb['rect'].set_on(v.rect_mode)
        self.tb['amove'].set_on(g.amove)
        self.tb['pause'].lab.text = 'Reprise' if g.paused else 'Pause'
        self.tb['pause'].pic.set('i_play' if g.paused else 'i_pause')
        if sig != self.sig:
            self.sig = sig
            self.bar.clear_widgets()
            self.cardbox.clear_widgets()
            self.cards = []
            if g.over:
                text = '[b][size=20sp]%s[/size][/b]\n%s' % (g.over, g.reason)
                if self.mode == 'campaign' and g.winner == me:
                    text += '\n[i]%s[/i]' % campaign.CAMPAIGNS[self.cur_fac]['missions'][self.cur_idx]['win']
                self.bar.add_widget(lbl(text, 12, halign='left', size_hint=(1, 1)))
                b = BigBtn('Continuer', 'i_ok', style='ui_btn_on', size=16, size_hint=(None, 1), width=dp(190))
                b.bind(on_release=lambda *_: self.finish_game())
                self.bar.add_widget(b)
            else:
                self.bar.add_widget(self.portrait)
                self.bar.add_widget(self.info)
                if g.placing:
                    self.bar.add_widget(Widget())
                    for lab, ic, fn in (('Poser ici', 'i_ok', self.confirm_place), ('Annuler', 'i_cancel', lambda: setattr(g, 'placing', None))):
                        c = Card(lab, (0, 0), ic, size_hint=(None, 1), width=dp(96))
                        c.bind(on_release=lambda *_, f=fn: self.press(f))
                        self.bar.add_widget(c)
                else:
                    self.bar.add_widget(self.scroll)
                    for a in acts:
                        desc = a['d'].get('desc') or a.get('locked') or ROLE_F.get((g.fac[me], a['kind'])) or ROLE.get(a['kind'], '')
                        c = Card(a['d']['label'], a['d']['cost'], self.card_icon(a), desc, size_hint=(None, 1), width=dp(80))
                        c.bind(on_release=lambda *_, f=a['fn'], cc=c: None if cc.long else self.press(f))
                        self.cardbox.add_widget(c)
                        self.cards.append(c)
        if not g.over and not g.placing:
            for c, a in zip(self.cards, acts):
                s_ = a.get('state', 'ready')
                info, dim, ok = '', False, a['ok']
                if a.get('locked'):
                    info, dim, ok = 'Verrouillé', True, True
                elif s_ == 'done':
                    info, dim, ok = 'Acquis', True, True
                elif s_ == 'locked':
                    info, dim, ok = 'Verrouillé', True, True
                elif s_ == 'busy':
                    b_ = next((e for e in g.ents if e.res and e.team == me and e.res[0] == a['kind'][5:]), None)
                    info, ok = ('%d %%' % int(100 * b_.res[1] / g.tech(me, b_.res[0])['time']) if b_ else 'En cours'), True
                if a['kind'] == 'ability':
                    if a.get('active', 0) > 0:
                        info, ok = 'Actif %ds' % (int(a['active']) + 1), True
                    elif a.get('cd', 0) > 0:
                        info, dim, ok = '%d s' % (int(a['cd']) + 1), True, True
                c.set_ok(ok)
                c.set_info(info, dim)

    def toggle_rect(self):
        self.view.rect_mode = not self.view.rect_mode
        if self.view.rect_mode:
            self.g.say("Glissez sur l'écran pour entourer vos unités")

    def toggle_amove(self):
        self.g.amove = not self.g.amove
        if self.g.amove:
            self.g.say('Attaquer en route : touchez la destination')

    def toggle_pause(self):
        if self.view.net:
            self.g.say('Pause impossible en multijoueur')
            return
        self.g.paused = not self.g.paused

    def confirm_place(self):
        g, v = self.g, self.view
        if v.ghost and g.build_with_selected(g.placing, *v.ghost):
            g.placing = None
        else:
            g.say('Emplacement invalide (près de vos bâtiments, sans obstacle)')


if __name__ == '__main__':
    RTSApp().run()
