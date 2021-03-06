#misc imports
import numpy as np
import threading
import random

#cranknicolson imports
from dsexperiment import DSexperiment
from dsexperiment import create_experiment_from_files

#kivy imports
from kivy.app import App
from kivy.uix.widget import Widget
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.popup import Popup
from kivy.properties import ObjectProperty, NumericProperty
from kivy.graphics import Rectangle
from kivy.graphics.texture import Texture
from kivy.graphics import Color
from kivy.clock import Clock

class MeasuresPopup(Popup):
    m_rectangle = ObjectProperty()
    classic_switch = ObjectProperty()
    measurements = []
    V = []
    size_y = 1

    def __init__(self, *args, **kwargs):
        super(MeasuresPopup, self).__init__(*args, **kwargs)
        self.classic_switch.bind(active=self.draw_measurements)

    def draw_measurements(self, *args, **kwargs):
        self.m_rectangle.canvas.clear()
        self.title = "Measuring screen"

        with self.m_rectangle.canvas:

            x0 = self.m_rectangle.pos[0]
            y0 = self.m_rectangle.pos[1]
            w = self.m_rectangle.size[0]
            h = self.m_rectangle.size[1]

            if self.classic_switch.active:
                V = np.array([np.sum(self.V, axis = 1)]*self.V.shape[0])
                Vo = np.max(V)
                self.texture_V = Texture.create(size = V.shape[::-1], colorfmt = "rgba", bufferfmt = "uint")

                M = np.zeros((V.shape[0], V.shape[1], 4), dtype = np.uint8)
                M[:,:,0] = (255*V/Vo).astype(np.uint8)
                M[:,:,1] = (255*(Vo-V)/Vo).astype(np.uint8)
                M[:,:,3] = np.full(M[:,:,0].shape, 255//8)

                self.texture_V.blit_buffer( M.reshape(M.size), colorfmt = "rgba")

                Color(1., 1., 1.)
                Rectangle(texture = self.texture_V, pos = (x0, y0), size = (w, h))
            else:
                Color(0., .25, 0)
                Rectangle(pos = (x0, y0), size = (w, h))

            np_mes = np.array(self.measurements)
            self.zoom = w/self.size_y
            if len(self.measurements) > 0:
                self.zoomz = h/(2*np.max(np.absolute(np_mes[:,2])))
            xc = x0 + w/2
            yc = y0 + h/2

            Color(1., 1., 1.)
            Rectangle(pos = (x0, y0+h/2), size = (w, 1))
            Rectangle(pos = (x0 + w/2, y0), size = (1, h))

            Color(0, 1. ,0)
            for measure in self.measurements:
                Rectangle(pos = (measure[1]*self.zoom, yc + measure[2]*self.zoomz), size = (4, 4))



class DoubleSlitScreen(BoxLayout):
    #Objects binded from .kv file
    p_rectangle = ObjectProperty()
    playpause_button = ObjectProperty()
    frame_slider = ObjectProperty()
    speed_slider = ObjectProperty()
    normalize_switch = ObjectProperty()
    screen_pos_slider = ObjectProperty()
    screen_width_slider = ObjectProperty()
    compute_button = ObjectProperty()
    progress_bar = ObjectProperty()
    label_info = ObjectProperty()
    loop_switch = ObjectProperty()
    hundred_switch = ObjectProperty()

    slider_d = ObjectProperty()
    n_label = ObjectProperty()
    #slider_sx = ObjectProperty()
    slider_sy = ObjectProperty()

    #Objects created here
    frame = NumericProperty(0) #current frame
    frames = NumericProperty(0) #total number of frames
    texture = ObjectProperty() #texture object (initialized at create_texture)
    zoom = NumericProperty(1) #this value autoadjusts when calling blit_P

    #Drawing parameters
    #size and position of he heatmap
    wh = 0
    hh = 0
    xh = 0
    yh = 0

    #Playback status and settings
    speed = NumericProperty(4)
    playing = False
    normalize_each_frame = False
    loop = False

    #Simulation results
    computing = False
    computed = False
    should_compute = False
    Pt = None
    times = None
    maxP = 1

    measures_popup = ObjectProperty()

    def __init__(self, *args, **kwargs):
        super(DoubleSlitScreen, self).__init__(*args, **kwargs)

        #Tries to load old simulation, in case there isn't any, it creates an
        #empty experiment with only psi(t=0)
        print("Trying to load last simulation")
        try:
            self.experiment = create_experiment_from_files("lastsim")
            print("Last simulation loaded correctly")
            self.computation_done(save = False)
        except FileNotFoundError:
            print("Could not find last simulation, creating new one...")
            self.experiment = DSexperiment()
            self.experiment.set_gaussian_psi0(p0x = 150/self.experiment.Lx)
            self.maxP = np.max(self.experiment.Pt)

        #Updates the UI with the values from the experiment
        self.n_label.text = str(self.experiment.n)
        #self.slider_sx.value = self.experiment.sx
        self.slider_sy.value = self.experiment.sy
        self.slider_d.value = self.experiment.d

        #default value for the normalize_switch
        self.normalize_switch.active = True

        self.create_textures()

    #Drawing functions
    def create_textures(self):
        """
        Creates the textures that will be used (for the wavefunction and for the potential (slits) )
        """
        self.texture_psi = Texture.create(size = self.experiment.Pt[0].shape[::-1], colorfmt = "luminance", bufferfmt = "uint")
        self.texture_V = Texture.create(size = self.experiment.Pt[0].shape[::-1], colorfmt = "rgba", bufferfmt = "uint")

    def blit_P(self, P):
        """
        This function draws the heatmap for P centered at
        P is a 2d numpy array
        """

        #Basically if white should represent the maximum value of P at each frame
        #or should represent the maximum value of all frames
        if self.normalize_each_frame:
            max = np.max(P)
        else:
            max = self.maxP

        #Stores the P matrix in the texture object
        #this texture is created in the method creature_texture and already has the size
        #It's a gray-scale texture so value must go from 0 to 255 (P/self.maxP)*255
        #It must be an array of unsigned 8bit integers. And also it has to be flattened

        self.texture_psi.blit_buffer( ((P/max)*255).astype(np.uint8).reshape(P.size), colorfmt = "luminance")

        #Draws the box walls and the
        with self.p_rectangle.canvas:
            #Determines the size of the box:
            #Full height
            self.zoom = self.p_rectangle.height/P.shape[0]
            #If full height implies cutting by the sides, it uses full width
            if P.shape[1]*self.zoom > self.p_rectangle.width:
                #Full width
                self.zoom = self.p_rectangle.width/P.shape[1]

            self.wh = P.shape[1]*self.zoom
            self.hh = P.shape[0]*self.zoom

            self.xh = self.p_rectangle.pos[0] + self.p_rectangle.width/2 - self.wh/2
            self.yh = self.p_rectangle.pos[1] + self.p_rectangle.height/2 - self.hh/2

            Color(1., 0, 0) #Red
            #box wall
            Rectangle(pos = (self.xh-5, self.yh-5), size = (self.wh+10, self.hh+10))

            #Heatmap
            Color(1., 1., 1.) #White
            Rectangle(texture = self.texture_psi, pos = (self.xh, self.yh), size = (self.wh, self.hh))


    def draw_slits(self):
        """
        Draws the slits (heatmap of the potential energy)
        """
        with self.p_rectangle.canvas:
            V = self.experiment.V
            Vo = self.experiment.Vo

            M = np.zeros((V.shape[0], V.shape[1], 4), dtype = np.uint8)
            M[:,:,0] = (255*V/Vo).astype(np.uint8)
            M[:,:,3] = M[:,:,0]

            self.texture_V.blit_buffer( M.reshape(M.size), colorfmt = "rgba")

            Rectangle(texture = self.texture_V, pos = (self.xh, self.yh), size = (self.wh, self.hh))


    def draw_measures(self):
        """
        Draws points representing measures in the main UI
        """

        with self.p_rectangle.canvas:
            scale = self.zoom/self.experiment.dx

            #Measuring screen
            Color(0, 1., 0, 0.25)
            Rectangle(pos = (self.xh + self.experiment.mp*self.zoom, self.yh), size = (self.experiment.mw*self.zoom, self.hh))

            Color(0, 1., 0)
            for measure in self.experiment.measurements:
                Rectangle(pos = (self.xh + measure[0]*self.zoom, self.yh + measure[1]*self.zoom), size = (self.zoom, self.zoom))

    def open_measures_popup(self):
        """
        Opens a popup with the measuring screen
        """
        self.measures_popup.measurements = self.experiment.measurements
        self.measures_popup.V = self.experiment.V
        self.measures_popup.size_y = self.experiment.Pt[0].shape[0]
        self.measures_popup.open()


    def computation_update(self, msg, x):
        """
        This is called by the thread computing the simulation
        """
        self.progress_bar.value = 100*x
        self.label_info.text = "[b]Computing: [/b]"
        self.label_info.text += msg

    def computation_done(self, save = True):
        """
        This is called when the simulation has been completed
        """
        self.frames = self.experiment.Pt.shape[0]
        self.frame_slider.max = self.frames - 1
        self.maxP = np.max(self.experiment.Pt)

        self.create_textures()

        self.computed = True
        self.computing = False
        self.should_compute = False

        if save:
            self.experiment.save_to_files("lastsim")

    def compute(self):
        """
        This is called when the compute button is pressed
        """
        if not self.computing:
            self.experiment.set_gaussian_psi0(p0x = 150/self.experiment.Lx)
            self.experiment.compute_evolution(update_callback = self.computation_update, done_callback = self.computation_done)

            self.playing = False
            self.computed = False
            self.computing = True

            self.frame = 0

    #Playback functions
    def playpause(self):
        self.playing = not self.playing

    def change_frame(self):
        self.playing = False
        self.frame = int(self.frame_slider.value)

    def measure(self, N = 1):
        self.experiment.measure(N)

    def remove_measurements(self):
        self.experiment.clear_measurements()

    #Loops 1, Loops 2, Javier Blanquez
    def add_slits(self, a):
        """
        Adds or removes slits
        """
        self.should_compute = self.experiment.update_slits(n = self.experiment.n + a) or self.should_compute
        self.n_label.text = str(self.experiment.n)



    def update(self, dt):
        self.playpause_button.disabled = not self.computed or self.should_compute
        self.compute_button.disabled = self.computing

        if self.playing:
            self.playpause_button.text = "Pause experiment"
        else:
            self.playpause_button.text = "Start experiment"

        self.frame_slider.disabled = not self.computed

        self.normalize_each_frame = self.normalize_switch.active

        self.speed = int(self.speed_slider.value)

        mp = int(self.experiment.Pt[0].shape[1]*self.screen_pos_slider.value)
        mw = int(self.screen_width_slider.value)

        if self.experiment.update_measure_screen(mp, mw):
            self.remove_measurements()

        self.should_compute = self.experiment.update_slits(sy = self.slider_sy.value, d = self.slider_d.value) or self.should_compute

        if self.should_compute:
            self.compute_button.background_color = (0.0, 1.0, 0.0, 1.0)
            self.playing = False
            self.remove_measurements()
        else:
            self.compute_button.background_color = (1.0, 1.0, 1.0, 1.0)

        #Info label:

        if not self.computing:
            self.label_info.text = "[b]Info: [/b]"
            if self.should_compute or not self.computed:
                self.label_info.text += "Click [i]Compute[/i]"
            elif not self.playing:
                self.label_info.text += "Click [i]Start experiment[/i]"
            else:
                self.label_info.text += "Running experiment"

        if self.playing:
            self.p_rectangle.canvas.clear()
            self.progress_bar.value = 100*self.frame/self.frames
            self.blit_P(self.experiment.Pt[self.frame])
            self.draw_slits()
            self.draw_measures()
            self.frame = (self.frame+self.speed)

            if self.frame >= self.frames:
                if self.hundred_switch.active:
                    self.measure(100)
                else:
                    self.measure()

                if self.loop_switch.active:
                    self.frame = self.frame%self.frames
                else:
                    self.frame = 0
                    self.playing = False


            self.frame_slider.value = self.frame

        else:
            if not self.computing:
                self.p_rectangle.canvas.clear()
                self.blit_P(self.experiment.Pt[self.frame])
                self.draw_slits()
                self.draw_measures()



class DoubleSlitApp(App):
    def build(self):
        random.seed()
        screen = DoubleSlitScreen()
        screen.measures_popup = MeasuresPopup()
        Clock.schedule_interval(screen.update, 1.0 / 30.0)
        return screen

if __name__ == "__main__":
    DoubleSlitApp().run()
