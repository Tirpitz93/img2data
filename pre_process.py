"""
Filter Images based on quality parameters as best as possible to reduce the number of images to be processed by the model.

Normalizes the images to a consistent exposure and brightness level to improve the accuracy of the model.

Flags images based on the following parameters:
    - shared similarity between images
    - motion blur
    - brightness
    - depth of field (region of image with high frequency content)

"""
import threading

import cv2
import numpy as np
from tkinter import filedialog, Tk, ttk, filedialog, colorchooser
import tkinter as tk
from PIL import ImageTk as itk
from PIL import Image

import accordion
from accordion import Accordion


class FilterBase:
    def __init__(self):
        # self.image_pil = self.load_image(self.image_path)
        self.parameters = {}
        # self.enabled = True  # Default to enabled, can be overridden by subclasses

    @property
    def enabled(self):
        return self.parameters.get("enabled", {}).get("default", True)

    def paint_overlays(self, canvas, *args, **kwargs):
        """
        Paint the filters output onto the current canvas. This is a placeholder method that should be overridden by subclasses to implement specific filter overlays.
        for example
        :param canvas:
        :param colour:
        :return:
        """

        pass

    def get_parameters(self) -> dict[str, dict]:
        """
        Get the parameters for the filter. This is a placeholder method that should be overridden by subclasses to implement specific filter parameters.
        this will be called by the filters control class to great the control widgets, expose all user adjustable parameters for the filter here.
        :return:
        """
        pass

    def set_parameters(self, params: dict):
        """
        Set the parameters for the filter. This is a placeholder method that should be overridden by subclasses to implement specific filter parameters.
        this will be called by the filters control class to set the parameters from the control widgets, expose all user adjustable parameters for the filter here.
        :param params:
        :return:
        """
        self.parameters.update(params)

    def mask(self, image: Image.Image, *args, **kwargs) -> Image.Image:
        """
        return a single channel single bit mask image of the filter output, this will be used to overlay the filter output on the image in the canvas.

        active pixels are white, inactive pixels are black, the mask will be resized to the canvas size before being overlayed on the image.

        for example
        :param canvas:
        :param colour:
        :return:
        """
        pass

    @property
    def stats(self) -> dict:
        """
        return a dictionary of statistics about the filter output, this will be used to display the filter output in the filters table.
        for example: % area of image that matches the filter
        distribution of filter values across the image
        :return:
        """
        pass


class FilterBrightness(FilterBase):
    def __init__(self):
        super().__init__()
        self.gray_image = None  # Store the grayscale version of the image for brightness calculations
        self.parameters = {
            "brightness_threshold": {"label": "Brightness Threshold", "type": "int", "default": 100, "range": (0, 255)},
            "brightness_colour": {"label": "Brightness Colour", "type": "colour", "default": "#FF0000"},
        }

    def compute(self, image, *args, **kwargs) -> Image.Image:
        """
        return a single channel single bit mask image of the brightness filter output, this will be used to overlay the filter output on the image in the canvas.
        active pixels are white, inactive pixels are black, the mask will be resized to the canvas size before being overlayed on the image.
        :param canvas:
        :param colour:
        :return:
        """
        if self.enabled is False:
            return Image.new("L", image.size, 0)  # Return a black mask if the filter is disabled

        # Convert PIL image to OpenCV format
        image_cv = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)

        # Convert to grayscale
        self.gray_image = cv2.cvtColor(image_cv, cv2.COLOR_BGR2GRAY)

    def get_parameters(self) -> dict[str, dict]:
        """
        Get the parameters for the brightness filter.
        :return: Dictionary of parameters
        """
        return self.parameters

    def mask(self, image, *args, **kwargs) -> Image.Image:
        brightness_threshold = self.parameters.get("brightness_threshold", {}).get("default", 100)
        brightness_colour = self.parameters.get("brightness_colour", {}).get("default", "#FF0000")
        if self.gray_image is None:
            self.compute(image)
        _, mask = cv2.threshold(self.gray_image, brightness_threshold, 255, cv2.THRESH_BINARY)

        # show pil image of mask
        # filter white areas of mask
        mask_pil = Image.fromarray(mask, mode='L')

        return mask_pil


class FilterFocus(FilterBase):
    def __init__(self):
        super().__init__()
        self.parameters = {
            "focus_threshold": {"label": "Focus Threshold", "type": "int", "default": 100, "range": (0, 255)},
            "focus_colour": {"label": "Focus Colour", "type": "colour", "default": "#00FF00"},
        }
        self.laplacian = None  # Store the Laplacian of the image for focus calculations

    def compute(self, image, *args, **kwargs) -> Image.Image:
        """
        return a single channel single bit mask image of the focus filter output, this will be used to overlay the filter output on the image in the canvas.
        active pixels are white, inactive pixels are black, the mask will be resized to the canvas size before being overlayed on the image.
        :param canvas:
        :param colour:
        :return:
        """
        if self.enabled is False:
            return Image.new("L", image.size, 0)  # Return a black mask if the filter is disabled
        focus_threshold = self.parameters.get("focus_threshold", {}).get("default", 100)
        focus_colour = self.parameters.get("focus_colour", {}).get("default", "#00FF00")

        # Convert PIL image to OpenCV format
        image_cv = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)

        # Convert to grayscale
        gray_image = cv2.cvtColor(image_cv, cv2.COLOR_BGR2GRAY)

        # Compute Laplacian to measure focus
        self.laplacian = cv2.Laplacian(gray_image, cv2.CV_64F)
        focus_measure = np.var(self.laplacian)
        max_focus_measure = np.max(np.abs(self.laplacian))
        print(f"Focus measure: {focus_measure}, Max focus measure: {max_focus_measure}")
        # scale laplacian to 0-255
        self.laplacian = cv2.convertScaleAbs(self.laplacian, alpha=255.0 / max_focus_measure)

    def mask(self, image, *args, **kwargs) -> Image.Image:
        # Create a mask for focused areas
        if self.laplacian is None:
            self.compute(image)
        _, mask = cv2.threshold(self.laplacian.astype(np.uint8),self.parameters.get("focus_threshold", {}).get("default", 100), 255, cv2.THRESH_BINARY)

        mask_pil = Image.fromarray(mask, mode='L')

        return mask_pil


def get_parameters(self) -> dict[str, dict]:
    """
    Get the parameters for the focus filter.
    :return: Dictionary of parameters
    """
    return self.parameters


class FilterControlsBase(accordion.Chord):
    def __init__(self, master: Accordion, filter: FilterBase, *args, **kwargs):
        super().__init__(master, title=filter.__class__.__name__)
        self.master = master
        self.filter = filter
        # self.pack(side=tk.RIGHT, fill=tk.Y)
        self.create_widgets()

    def on_parameter_change(self, param_name, value):
        """
        Callback function to handle parameter changes from the control widgets.
        :param param_name: Name of the parameter that changed
        :param value: New value of the parameter
        """
        self.filter.set_parameters({param_name: {"default": value}})
        # Optionally, you can trigger a repaint of the overlays here if needed
        self.master.master.update_canvas()  # Assuming the master has a method to update the canvas

    def create_widgets(self):
        params = self.filter.get_parameters()
        enabled = self.filter.parameters.get("enabled", {}).get("default", True)
        enable_label = tk.Label(self, text="Enable Filter")
        enable_label.pack()
        enable_var = tk.BooleanVar(value=enabled)
        enable_check = tk.Checkbutton(self, variable=enable_var,
                                      command=lambda: self.on_parameter_change("enabled", enable_var.get()))
        enable_check.pack()
        if params is None:
            return
        for param_name, param_info in params.items():
            label = param_info.get("label", param_name)
            type = param_info.get("type", "int")
            default = param_info.get("default", 0)
            range = param_info.get("range", (0, 100))
            if type == "int":
                label_widget = tk.Label(self, text=label)
                label_widget.pack()
                scale_widget = tk.Scale(self, from_=range[0], to=range[1], orient=tk.HORIZONTAL)
                scale_widget.set(default)
                scale_widget.pack()

                # on mouse release, call on_parameter_change with the current value of the scale
                scale_widget.bind("<ButtonRelease-1>", lambda event, param_name=param_name,
                                                              scale_widget=scale_widget: self.on_parameter_change(
                    param_name, int(scale_widget.get())))

                # scale_widget.config(
                #     command=lambda value, param_name=param_name: self.on_parameter_change(param_name, int(value)))
            if type == "float":
                label_widget = tk.Label(self, text=label)
                label_widget.pack()
                scale_widget = tk.Scale(self, from_=range[0], to=range[1], orient=tk.HORIZONTAL, resolution=0.01)
                scale_widget.set(default)
                scale_widget.pack()
                # on mouse release, call on_parameter_change with the current value of the scale
                scale_widget.bind("<ButtonRelease-1>", lambda event, param_name=param_name,
                                                              scale_widget=scale_widget: self.on_parameter_change(
                    param_name, float(scale_widget.get())))
                # scale_widget.config(
                #     command=lambda value, param_name=param_name: self.on_parameter_change(param_name, float(value)))
            if type == "bool":
                var = tk.BooleanVar(value=default)
                check_widget = tk.Checkbutton(self, text=label, variable=var)
                check_widget.pack()
                check_widget.config(
                    command=lambda param_name=param_name, var=var: self.on_parameter_change(param_name, var.get()))
            if type == "str":
                label_widget = tk.Label(self, text=label)
                label_widget.pack()
                entry_widget = tk.Entry(self)
                entry_widget.insert(0, default)
                entry_widget.pack()
                entry_widget.bind("<FocusOut>", lambda event, param_name=param_name,
                                                       entry_widget=entry_widget: self.on_parameter_change(param_name,
                                                                                                           entry_widget.get()))
            if type == "colour":
                label_widget = tk.Label(self, text=label)
                label_widget.pack()
                colour_button = tk.Button(self, text="Select Colour", command=lambda: self.select_colour(param_name))
                colour_button.pack()
                colour_var = tk.StringVar(value=default)
                colour_button.config(command=lambda: self.select_colour(param_name, colour_var))
                colour_label = tk.Label(self, textvariable=colour_var)
                colour_label.pack()

    def select_colour(self, param_name, colour_var):
        colour_code = colorchooser.askcolor(title="Choose colour")[1]
        if colour_code:
            colour_var.set(colour_code)
            self.filter.get_parameters()[param_name]["default"] = colour_code
        self.master.update_canvas()  # Assuming the master has a method to update the canvas


def rgb_to_int(colour):
    """
    Convert a hex colour string to an integer representation.
    :param colour: Hex colour string (e.g., "#FF0000")
    :return: Integer representation of the colour
    """
    colour = colour.lstrip('#')
    return int(colour, 16)


class ImageTab(tk.Frame):
    def __init__(self, master, image_path):
        super().__init__(master)
        self.image_path = image_path
        self.image_pil = self.load_image(self.image_path)
        self.canvas = tk.Canvas(self, width=self.winfo_width(), height=self.winfo_height(), bg="white")
        self.canvas.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        # self.update_canvas()
        self.tk_image = None  # Placeholder for the PhotoImage object
        self.update_in_progress = tk.IntVar()  # Semaphore to indicate if an update is in progress
        self.update_in_progress.trace_add("write", self.on_update_in_progress_change)  # Trace changes to the variable

    def on_update_in_progress_change(self, *args):
        if self.update_in_progress.get() > 0:
            print("Update in progress...")
        else:
            print("Update completed.")
            self.update_canvas()  # Call update_canvas when the update is completed

    def load_image(self, path):
        # Load image using OpenCV
        image = cv2.imread(path)
        # Convert BGR to RGB
        image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        # Convert to PIL Image
        return Image.fromarray(image)

    def update_canvas(self):
        self.canvas.delete("all")

        self.canvas.create_rectangle(0, 0, self.winfo_width() - 4, self.winfo_height(),
                                     fill="white")  # Placeholder for empty canvas
        if self.image_pil is not None:
            # create a resized version of the image to fit the canvas while maintaining aspect ratio
            self.tk_image = itk.PhotoImage(self.image_pil.resize((self.winfo_width(), self.winfo_height())))
            print(f"Frame size: {self.winfo_width()}x{self.winfo_height()}")
            print(F"Canvas size: {self.canvas.winfo_width()}x{self.canvas.winfo_height()}")
            print(f"Image size: {self.image_pil.width}x{self.image_pil.height}")
            print(f"Resized image size: {self.tk_image.width()}x{self.tk_image.height()}")
            self.canvas.config(width=self.winfo_width() - 4, height=self.winfo_height())
            (self.canvas.create_image
             (0, 0, anchor=tk.NW, image=self.tk_image))
            for filter_control in self.master.master.filter_controls:
                filter_instance = filter_control.filter
                self.apply_filter_mask(filter_instance)

    def apply_filter_mask(self, filter: FilterBase):
        """Apply filters mask transparently over the image on the canva

        :param filter: FilterBase: The filter to apply
        get the mask from the filter and overlay it on the image on the canvas, the mask will be resized to the canvas size before being overlayed on the image
        create a new transparent image with the same size as the canvas and paste the mask on it, then overlay the transparent image on the canvas
        set transparency where the mask is black, and the mask colour where the mask is white, the mask colour is set in the filter parameters, set colour to the filter parameter "brightness_colour" if it exists.
        set transparency to 128 with colour to the filter parameter "brightness_colour" if it exists, otherwise set transparency to 128 with colour to red.

        """
        mask = filter.mask(self.image_pil)
        mask = mask.resize((self.canvas.winfo_width(), self.canvas.winfo_height()))
        mask_colour = filter.parameters.get("brightness_colour", {}).get("default", "#FF0000")
        mask_colour_int = rgb_to_int(mask_colour)
        # create a new transparent image with the same size as the canvas
        transparent_image = Image.new("RGBA", (self.canvas.winfo_width(), self.canvas.winfo_height()), (0, 0, 0, 0))
        # paste the mask on the transparent image
        alpha_mask = mask.convert("L").point(lambda p: 128 if p > 0 else 0)  # Set alpha to 128 where mask is white
        coloured_mask = Image.new("RGBA", mask.size, mask_colour)
        transparent_image.paste(coloured_mask, (0, 0), alpha_mask)
        # overlay the transparent image on the canvas
        self.tk_mask_image = itk.PhotoImage(transparent_image)
        self.canvas.create_image(0, 0, anchor=tk.NW, image=self.tk_mask_image)


class ImageFilterBuilder(Tk):
    def __init__(self):
        super().__init__()
        self.title("Image Filter Builder")
        self.geometry("1200x800")

        # create main Menu
        self.menu = tk.Menu(self)
        self.config(menu=self.menu)
        self.file_menu = tk.Menu(self.menu, tearoff=0)
        self.file_menu.add_command(label="Open Image", command=self.open_image)
        self.file_menu.add_command(label="Open Folder", command=self.open_folder)

        self.file_menu.add_command(label="Save Filtered Images", command=self.save_filtered_images)
        self.menu.add_cascade(label="File", menu=self.file_menu)

        self.tabs = []

        # create notebook for images
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.notebook.bind("<<NotebookTabChanged>>", lambda event: self.update_canvas())
        # middle click to close tab
        self.notebook.bind("<Button-2>", lambda event: self.close_tab(event))

        # create a frame for the controls
        self.controls_frame = Accordion(self, accordion_style={'title_bg': 'ghost white', 'title_fg': 'black',
                                                               'highlight': 'white smoke'})
        self.filters = [FilterBrightness, FilterFocus]  # Add more filters here as needed
        self.filter_controls = []
        for filter_class in self.filters:
            filter_instance = filter_class()  # Pass None for image_path, will be set later

            _chord = FilterControlsBase(self.controls_frame, filter_instance)
            self.filter_controls.append(_chord)
        self.controls_frame.pack(side=tk.RIGHT, fill=tk.Y, padx=5, pady=5)
        self.controls_frame.append_chords(self.filter_controls)

    def open_image(self):
        # open file dialog to select image
        file_path = filedialog.askopenfilename(filetypes=[("Image files", "*.jpg *.png *.jpeg *.bmp *.tiff")])
        if file_path:
            self.load_image(file_path)

        pass

    def update_canvas(self):
        # update the currently visible tab's canvas with the image

        tab: ImageTab = self.notebook.nametowidget(
            self.notebook.select())  # Get the canvas widget from the currently selected tab
        for filter_control in self.filter_controls:
            filter_instance = filter_control.filter
            tab.apply_filter_mask(filter_instance)
        tab.update_canvas()  # Call the update_canvas method of the ImageTab class to redraw the image and overlays

    def load_image(self, path):
        # Load image using OpenCV
        self.image_path = path
        image = cv2.imread(path)
        # Convert BGR to RGB
        image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        # Convert to PIL Image
        from PIL import Image
        self.image_pil = Image.fromarray(image)
        print(f"Loaded image: {self.image_path}")
        # create a new tab for the image
        image_tab = ImageTab(self.notebook, self.image_path)
        self.notebook.add(image_tab, text=self.image_path.split("/")[-1])
        self.tabs.append(image_tab)
        # create a canvas to display the image

        image_tab.update_canvas()
        return self.image_pil

    def open_folder(self):
        pass

    def save_filtered_images(self):
        pass

    def close_tab(self, event):
        # close the currently selected tab
        current_tab = self.notebook.select()
        if current_tab:
            self.notebook.forget(current_tab)
            self.tabs.remove(self.notebook.nametowidget(current_tab))
            self.update_canvas()

    def process_filter_in_thread(self, image_path, filters):
        """
        Process the filters in a separate thread to avoid blocking the GUI.
        :param image_path: Path to the image to be processed
        :param filters: List of filter instances to be applied
        """
        self.update_in_progress.set(
            self.update_in_progress.get() + 1)  # Set the semaphore to indicate that an update is in progress
        worker = self.FilterWorker(image_path, filters)
        worker.start()

    class FilterWorker(threading.Thread):
        def __init__(self, image_path, filters):
            super().__init__()
            self.image_path = image_path
            self.filters = filters

        def run(self):
            # Load the image
            image = cv2.imread(self.image_path)
            # Convert BGR to RGB
            image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            # Convert to PIL Image
            from PIL import Image
            image_pil = Image.fromarray(image)

            # Apply each filter and save the result
            for filter in self.filters:
                mask = filter.compute(image_pil)
                # Save the mask or overlay it on the original image as needed
                mask.save(f"{self.image_path}_{filter.__class__.__name__}_mask.png")


if __name__ == "__main__":
    app = ImageFilterBuilder()
    app.load_image("C:\\python_projects\\img2data\\PDFXEdit_5sW4y9FizE.png")
    app.update_canvas()
    app.mainloop()
