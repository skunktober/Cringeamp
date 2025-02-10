import sys
import subprocess
import importlib
import os

def check_and_install_dependencies():
    packages = [
        ("pygame", "pygame"),
        ("PIL", "Pillow"),
        ("mutagen", "mutagen")
    ]
    missing = False
    for module_name, package_name in packages:
        try:
            importlib.import_module(module_name)
        except ImportError:
            missing = True
            subprocess.check_call([sys.executable, "-m", "pip", "install", package_name])
    if missing:
        os.execv(sys.executable, [sys.executable] + sys.argv)

check_and_install_dependencies()

import tkinter as tk
from tkinter import filedialog, ttk
import pygame
import time
import math
from PIL import Image, ImageTk
import re
from mutagen import File as MutagenFile

if sys.platform == 'win32':
    import ctypes
    ctypes.windll.user32.ShowWindow(ctypes.windll.kernel32.GetConsoleWindow(), 0)

class MusicPlayer:
    def __init__(self, root):
        self.root = root
        self.root.title("Cringeamp")
        self.root.geometry("400x750")
        self.root.resizable(False, False)
        
        if sys.platform == 'win32':
            self.root.iconbitmap("images/logo.ico")
        else:
            try:
                icon_image = Image.open("images/logo.png")
                icon_photo = ImageTk.PhotoImage(icon_image)
                self.root.iconphoto(True, icon_photo)
            except Exception as exception_instance:
                print(f"Error loading icon: {exception_instance}")

        if os.path.exists("images/background.png"):
            self.background_image = tk.PhotoImage(file="images/background.png")
            self.background_label = tk.Label(self.root, image=self.background_image, borderwidth=0)
            self.background_label.place(x=200, y=375, anchor='center')
            self.background_label.lower()

        pygame.mixer.init()

        self.playlist = []
        self.track_titles = []
        self.current_index = 0
        self.paused = False
        self.is_seeking = False
        self.song_length = 0
        self.text_id = None
        self.after_id = None
        self.scrub_after_id = None
        self.track_start_time = 0
        self.track_offset = 0
        self.scroll_direction = -1
        self.scroll_paused = False
        self.foreground_color = '#ffffff'

        self.background_color = '#1a1a1a'
        self.semi_bg = "#0d0d0d"

        # Variables for delayed start of playback
        self.delayed_start_pending = False
        self.delayed_start_identifier = None

        self.configure_styles()
        self.create_widgets()
        self.apply_theme()
        self.animate_waveform()

    def configure_styles(self):
        self.style = ttk.Style()
        self.style.theme_use('clam')
        self.style.configure('TButton', background=self.background_color, font=('Helvetica', 10), borderwidth=0)
        self.style.configure('Treeview', background=self.semi_bg, fieldbackground=self.semi_bg, font=('Helvetica', 10))
        self.style.map('Treeview', background=[('selected', 'blue')])
        self.style.configure('Volume.Horizontal.TScale', troughcolor='#404040', slidercolor='#ffffff', sliderwidth=20, padding=5)
        self.style.configure('Scrub.Horizontal.TScale', troughcolor='#404040', slidercolor='#ffffff', sliderwidth=15)
        self.style.configure('TLabel', font=('Helvetica', 10))
        self.style.configure('Time.TLabel', font=('Helvetica', 8))
        self.root.wm_attributes('-transparent', '000000')

    def create_widgets(self):
        self.logo_label = tk.Label(self.root, bg=self.root.cget('bg'))
        self.logo_label.pack(pady=(5, 5))
        self.update_logo_image()

        self.waveform_canvas = tk.Canvas(self.root, bg=self.background_color, height=50, highlightthickness=0)
        self.waveform_canvas.pack(fill=tk.X, padx=20, pady=(5, 5))

        self.current_song_canvas = tk.Canvas(self.root, bg=self.background_color, height=20, highlightthickness=0)
        self.current_song_canvas.pack(fill=tk.X, padx=20, pady=(0, 15))

        self.tree_frame = tk.Frame(self.root, bg=self.semi_bg)
        self.tree_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=(0, 15))
        self.tree = ttk.Treeview(self.tree_frame, columns=('song',), show='headings', selectmode='browse')
        self.tree.heading('song', text='TRACKS')
        self.tree.column('song', width=290, anchor=tk.W)
        vertical_scrollbar = ttk.Scrollbar(self.tree_frame, orient="vertical", command=self.tree.yview)
        vertical_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.configure(yscrollcommand=vertical_scrollbar.set)
        self.tree.pack(fill=tk.BOTH, expand=True)
        self.tree.bind("<Double-1>", self.on_tree_double_click)

        scrub_frame = tk.Frame(self.root, bg=self.background_color)
        scrub_frame.pack(fill=tk.X, padx=20, pady=(0, 15))
        self.time_elapsed = ttk.Label(scrub_frame, text="0:00", style='Time.TLabel')
        self.time_elapsed.pack(side=tk.LEFT)
        self.scrub_bar = ttk.Scale(scrub_frame, from_=0, to=100, orient=tk.HORIZONTAL,
                                   command=self.on_scrub_drag, style='Scrub.Horizontal.TScale')
        self.scrub_bar.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        self.time_remaining = ttk.Label(scrub_frame, text="-0:00", style='Time.TLabel')
        self.time_remaining.pack(side=tk.LEFT)
        self.scrub_bar.bind("<ButtonPress-1>", self.start_seeking)
        self.scrub_bar.bind("<ButtonRelease-1>", self.stop_seeking)

        volume_frame = tk.Frame(self.root, bg=self.background_color)
        volume_frame.pack(pady=(0, 15), padx=20, fill=tk.X)
        volume_frame.columnconfigure(1, weight=1)
        self.volume_label = ttk.Label(volume_frame, text="🔊", font=('Helvetica', 12))
        self.volume_label.grid(row=0, column=0, sticky="w", padx=(0, 10))
        self.volume_slider = ttk.Scale(volume_frame, from_=0, to=100, orient=tk.HORIZONTAL,
                                       command=self.set_volume, style='Volume.Horizontal.TScale', length=200)
        self.volume_slider.set(50)
        self.volume_slider.grid(row=0, column=1, sticky="ew")

        control_frame = tk.Frame(self.root, bg=self.background_color)
        control_frame.pack(pady=(0, 15), padx=20, fill=tk.X)
        self.play_button = ttk.Button(control_frame, text="▶", command=self.toggle_play_pause)
        self.play_button.pack(side=tk.LEFT, expand=True, padx=(0, 10))
        self.browse_button = ttk.Button(control_frame, text="📁", command=self.load_folder)
        self.browse_button.pack(side=tk.LEFT, expand=True)

    def animate_waveform(self):
        self.waveform_canvas.delete("waveform")
        canvas_width = self.waveform_canvas.winfo_width()
        canvas_height = self.waveform_canvas.winfo_height()
        if canvas_width < 10:
            self.root.after(50, self.animate_waveform)
            return

        mid_y = canvas_height // 2
        point_list = []
        phase = self.get_current_time() * 5
        maximum_amplitude = canvas_height // 3

        for x_position in range(0, canvas_width, 5):
            y_position = mid_y + (math.sin(x_position / 50 + phase) * maximum_amplitude +
                                  math.sin(x_position / 25 + phase * 1.5) * (maximum_amplitude // 2) +
                                  math.sin(x_position / 10 + phase * 2) * (maximum_amplitude // 3))
            y_position = max(2, min(canvas_height - 2, y_position))
            point_list.extend((x_position, y_position))

        self.waveform_canvas.create_line(
            point_list,
            fill=self.foreground_color,
            tags="waveform",
            smooth=True,
            width=2
        )
        self.root.after(50, self.animate_waveform)

    def update_logo_image(self):
        image_path = "images/logo.png"
        image_object = Image.open(image_path).convert("RGBA")
        desired_width = 150
        if image_object.width > desired_width:
            factor = image_object.width / desired_width
            new_width = int(image_object.width / factor)
            new_height = int(image_object.height / factor)
            image_object = image_object.resize((new_width, new_height), Image.LANCZOS)
        self.logo_image = ImageTk.PhotoImage(image_object)
        self.logo_label.configure(image=self.logo_image, bg=self.root.cget('bg'))

    def format_time(self, total_seconds):
        return f"{int(total_seconds // 60):02d}:{int(total_seconds % 60):02d}"

    def on_tree_double_click(self, event):
        selected_items = self.tree.selection()
        if selected_items:
            self.current_index = self.tree.index(selected_items[0])
            self.play_current_song()

    def play_current_song(self):
        if self.playlist:
            # Cancel any scheduled update tasks from a previous track
            if self.after_id:
                self.root.after_cancel(self.after_id)
                self.after_id = None
            if self.scrub_after_id:
                self.root.after_cancel(self.scrub_after_id)
                self.scrub_after_id = None
            if self.delayed_start_pending:
                self.root.after_cancel(self.delayed_start_identifier)
                self.delayed_start_pending = False
                self.delayed_start_identifier = None

            pygame.mixer.music.load(self.playlist[self.current_index])
            self.paused = False
            self.play_button.config(text="⏸")
            sound_object = pygame.mixer.Sound(self.playlist[self.current_index])
            self.song_length = sound_object.get_length()
            self.scrub_bar.config(to=self.song_length)
            self.track_offset = 0

            # Schedule the song to start playing after a 0.2 second delay.
            self.delayed_start_pending = True
            self.delayed_start_identifier = self.root.after(200, self.delayed_play)
            
            self.update_current_song_display()

    def delayed_play(self):
        self.delayed_start_pending = False
        self.delayed_start_identifier = None
        pygame.mixer.music.play()
        self.track_start_time = time.time()
        self.update_scrub_bar()

    def update_current_song_display(self):
        self.current_song_canvas.delete("all")
        if self.playlist:
            if self.track_titles and self.current_index < len(self.track_titles):
                song_name = self.track_titles[self.current_index]
            else:
                song_name = os.path.basename(self.playlist[self.current_index])
            canvas_width = self.current_song_canvas.winfo_width()
            self.text_id = self.current_song_canvas.create_text(
                canvas_width // 2, 10,
                text=song_name,
                anchor='center',
                fill=self.style.lookup('TLabel', 'foreground'),
                font=('Helvetica', 10, 'bold')
            )
            self.root.title(f"Cringeamp - {song_name}")
            self.current_song_canvas.update_idletasks()
            bounding_box = self.current_song_canvas.bbox(self.text_id)
            if bounding_box and (bounding_box[2] - bounding_box[0] > canvas_width):
                self.scroll_direction = -1
                self.scroll_paused = False
                self.animate_scroll()

    def animate_scroll(self):
        if not self.text_id:
            return
        current_x, current_y = self.current_song_canvas.coords(self.text_id)
        bounding_box = self.current_song_canvas.bbox(self.text_id)
        if not bounding_box:
            return
        text_width = bounding_box[2] - bounding_box[0]
        canvas_width = self.current_song_canvas.winfo_width()
        if text_width <= canvas_width:
            return

        if self.scroll_direction < 0 and current_x <= canvas_width - text_width:
            if not self.scroll_paused:
                self.scroll_paused = True
                self.root.after(3000, self.resume_scroll)
            return
        elif self.scroll_direction > 0 and current_x >= 0:
            if not self.scroll_paused:
                self.scroll_paused = True
                self.root.after(3000, self.resume_scroll)
            return

        self.current_song_canvas.move(self.text_id, self.scroll_direction, 0)
        self.after_id = self.root.after(50, self.animate_scroll)

    def resume_scroll(self):
        self.scroll_paused = False
        self.scroll_direction = -self.scroll_direction
        self.animate_scroll()

    def toggle_play_pause(self):
        # If a delayed start is pending and the user toggles, cancel the delayed start.
        if self.delayed_start_pending:
            self.root.after_cancel(self.delayed_start_identifier)
            self.delayed_start_pending = False
            self.delayed_start_identifier = None
            self.paused = True
            self.play_button.config(text="▶")
            return

        if not self.paused and pygame.mixer.music.get_busy():
            self.track_offset = self.get_current_time()
            pygame.mixer.music.pause()
            self.paused = True
            self.play_button.config(text="▶")
        else:
            if self.paused:
                pygame.mixer.music.unpause()
                self.track_start_time = time.time()
                self.paused = False
                self.play_button.config(text="⏸")
            else:
                self.play_current_song()

    def load_folder(self):
        folder_path = filedialog.askdirectory()
        if folder_path:
            self.playlist = []
            self.track_titles = []
            self.tree.delete(*self.tree.get_children())
            playlist_info = []
            file_list = [file_name for file_name in os.listdir(folder_path) if file_name.lower().endswith(('.mp3', '.wav', '.ogg', '.flac'))]
            for file_name in file_list:
                full_path = os.path.join(folder_path, file_name)
                fallback_title = os.path.splitext(file_name)[0]
                display_title = "▶ " + fallback_title
                sort_key = MusicPlayer.track_sort_key(file_name)
                try:
                    audio = MutagenFile(full_path, easy=True)
                    if audio and 'artist' in audio and 'title' in audio and 'tracknumber' in audio:
                        artist = audio['artist'][0].strip()
                        title = audio['title'][0].strip()
                        track_string = audio['tracknumber'][0]
                        track_match = re.match(r'(\d+)', track_string)
                        if track_match:
                            track_number = int(track_match.group(1))
                            display_title = "▶ " + f"{artist} - {title}"
                            sort_key = (0, track_number, fallback_title.lower())
                except Exception:
                    pass
                playlist_info.append((full_path, display_title, sort_key))
            playlist_info.sort(key=lambda information: information[2])
            for info in playlist_info:
                self.playlist.append(info[0])
                title_without_prefix = info[1]
                if title_without_prefix.startswith("▶ "):
                    title_without_prefix = title_without_prefix[2:].strip()
                self.track_titles.append(title_without_prefix)
                self.tree.insert('', tk.END, values=(info[1],))

    @staticmethod
    def track_sort_key(file_name, pattern=re.compile(r'^\s*(\d+)')):
        name_part, _ = os.path.splitext(file_name)
        match = pattern.match(name_part)
        if match:
            number_value = int(match.group(1))
            remaining_text = name_part[match.end():].strip().lower()
            return (0, number_value, remaining_text)
        else:
            return (1, name_part.lower())

    def set_volume(self, value):
        volume_level = float(value) / 100  # Convert to a float between 0.0 and 1.0.
        pygame.mixer.music.set_volume(volume_level)

    def start_seeking(self, event):
        self.is_seeking = True
        self.was_playing = pygame.mixer.music.get_busy() and not self.paused
        if self.scrub_after_id is not None:
            self.root.after_cancel(self.scrub_after_id)
            self.scrub_after_id = None
        if self.was_playing:
            self.track_offset = self.get_current_time()
            pygame.mixer.music.pause()
            self.paused = True
            self.play_button.config(text="▶")

    def stop_seeking(self, event):
        self.is_seeking = False
        seek_position = self.scrub_bar.get()
        pygame.mixer.music.set_pos(seek_position)
        self.track_offset = seek_position
        self.track_start_time = time.time()
        self.time_elapsed.config(text=self.format_time(seek_position))
        self.time_remaining.config(text=f"-{self.format_time(self.song_length - seek_position)}")
        if self.was_playing:
            pygame.mixer.music.unpause()
            self.paused = False
            self.play_button.config(text="⏸")
        self.update_scrub_bar()

    def on_scrub_drag(self, value):
        if self.is_seeking:
            current_time = float(value)
            self.time_elapsed.config(text=self.format_time(current_time))
            self.time_remaining.config(text=f"-{self.format_time(self.song_length - current_time)}")

    def get_current_time(self):
        if (not pygame.mixer.music.get_busy()) or self.paused or self.is_seeking:
            return self.track_offset
        else:
            return (time.time() - self.track_start_time) + self.track_offset

    def update_scrub_bar(self):
        if (not pygame.mixer.music.get_busy()) and (not self.paused) and (not self.is_seeking):
            self.current_index += 1
            if self.current_index >= len(self.playlist):
                self.current_index = 0
            self.play_current_song()
            return
        current_time_value = self.get_current_time()
        self.scrub_bar.set(current_time_value)
        self.time_elapsed.config(text=self.format_time(current_time_value))
        self.time_remaining.config(text=f"-{self.format_time(self.song_length - current_time_value)}")
        self.scrub_after_id = self.root.after(250, self.update_scrub_bar)

    def apply_theme(self):
        background_color = '#1a1a1a'
        foreground_color = '#ffffff'
        self.foreground_color = foreground_color
        self.root.config(bg=background_color)
        self.logo_label.config(bg=background_color)
        self.waveform_canvas.config(bg=background_color)
        self.style.configure('.', background=background_color, foreground=foreground_color)
        self.style.configure('Treeview', background=self.semi_bg, fieldbackground=self.semi_bg, foreground=foreground_color)
        self.style.configure('TButton', background=background_color, font=('Helvetica', 10), borderwidth=0)
        self.style.configure('TLabel', background=background_color, foreground=foreground_color)
        self.style.configure('Time.TLabel', background=background_color, foreground=foreground_color)
        self.style.configure('Volume.Horizontal.TScale', troughcolor='#404040', slidercolor=foreground_color, sliderwidth=20, padding=5)
        self.style.configure('Scrub.Horizontal.TScale', troughcolor='#404040', slidercolor=foreground_color, sliderwidth=15)
        self.current_song_canvas.config(bg=background_color)

if __name__ == "__main__":
    root_window = tk.Tk()
    application_instance = MusicPlayer(root_window)
    root_window.mainloop()
