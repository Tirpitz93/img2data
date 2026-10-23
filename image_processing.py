from PIL import Image
import cv2
import numpy as np

from tkinter import filedialog, Tk
import tkinter as tk

from TkToolTip import ToolTip


class LineTestBed(Tk):
    def __init__(self):
        super().__init__()
        self.title("Line Test Bed")
        self.geometry("800x1200")
        self.image_path = None
        self.image_pil = None
        self.edges = None
        self.lines = None
        self.selected_lines = None

        # Load image button
        self.load_button = tk.Button(self, text="Load Image", command=self.load_image)
        self.load_button.pack(pady=10)

        # Process image button
        self.process_button = tk.Button(self, text="Process Image", command=self.process_image)
        self.process_button.pack(pady=10)
        self.canvas = tk.Canvas(self, width=800, height=400, bg="white")
        self.canvas.pack(pady=10)
        self.line1 = None
        self.line2 = None

        self.stats   = tk.Frame(self)
        self.stats.pack(side=tk.BOTTOM, fill=tk.X, pady=10)
        self.stat3 = tk.Label(self.stats, text="Angle: ")
        self.stat3.grid(row=1, column=0, padx=10)


        self.length = tk.Label(self.stats, text="Length: ")
        self.length.grid(row=3, column=0, padx=10)


        self.stat1 = tk.Label(self.stats, text="Line 1: ")
        self.stat1.grid(row=0, column=1, padx=10)

        self.stat2 = tk.Label(self.stats, text="Line 2: ")
        self.stat2.grid(row=0, column=2, padx=10)

        self.l1angle = tk.Label(self.stats, text="")
        self.l1angle.grid(row=1, column=1, padx=10)

        self.l2angle = tk.Label(self.stats, text="")
        self.l2angle.grid(row=1, column=2, padx=10)

        self.l1length = tk.Label(self.stats, text="")
        self.l1length.grid(row=3, column=1, padx=10)

        self.l2length = tk.Label(self.stats, text="")
        self.l2length.grid(row=3, column=2, padx=10)

        self.collinear = tk.Label(self.stats, text="")
        self.collinear.grid(row=2, column=4, padx=10)

        self.angle = tk.Label(self.stats, text="")
        self.angle.grid(row=1, column=3, padx=10)
        self.unit_vector = tk.Label(self.stats, text="Unit Vector: ")
        self.unit_vector.grid(row=4, column=0, padx=10)
        self.l1unit = tk.Label(self.stats, text="")
        self.l1unit.grid(row=4, column=1, padx=10)
        self.l2unit = tk.Label(self.stats, text="")
        self.l2unit.grid(row=4, column=2, padx=10)

        self.product = tk.Label(self.stats, text="Dot Product: ")
        self.product.grid(row=5, column=0, padx=10)

        self.dot_product = tk.Label(self.stats, text="")
        self.dot_product.grid(row=5, column=3, padx=10)


        self.distance_from_corner_start = tk.Label(self.stats, text="Distance from Corner: ")
        self.distance_from_corner_start.grid(row=6, column=0, padx=10)
        self.l1distance_start = tk.Label(self.stats, text="")
        self.l1distance_start.grid(row=6, column=1, padx=10)
        self.l2distance_start = tk.Label(self.stats, text="")
        self.l2distance_start.grid(row=6, column=2, padx=10)

        self.distance_from_corner_end = tk.Label(self.stats, text="Distance from Corner: ")
        self.distance_from_corner_end.grid(row=7, column=0, padx=10)
        self.l1distance_end = tk.Label(self.stats, text="")
        self.l1distance_end.grid(row=7, column=1, padx=10)
        self.l2distance_end = tk.Label(self.stats, text="")
        self.l2distance_end.grid(row=7, column=2, padx=10)


        self.slope_label = tk.Label(self.stats, text="Slope: ")
        self.slope_label_tt = ToolTip(self.slope_label, msg="Slope of the detected line segments. Δy / Δx. A vertical line has an infinite slope.")
        self.slope_label.grid(row=2, column=0, padx=10)
        self.l1slope = tk.Label(self.stats, text="")
        self.l1slope.grid(row=2, column=1, padx=10)

        self.l2slope = tk.Label(self.stats, text="")
        self.l2slope.grid(row=2, column=2, padx=10)


        self.x_axis_score = tk.Label(self.stats, text="X Axis Score: ")
        self.x_axis_score_tt = ToolTip(self.x_axis_score, msg="Score indicating how well the detected line aligns with the expected X axis.")
        self.x_axis_score.grid(row=9, column=0, padx=10)

        self.y_axis_score = tk.Label(self.stats, text="Y Axis Score: ")
        self.y_axis_score_tt = ToolTip(self.y_axis_score, msg="Score indicating how well the detected line aligns with the expected Y axis.")

        self.y_axis_score.grid(row=10, column=0, padx=10)

        self.l1x_axis_score = tk.Label(self.stats, text="")
        self.l1x_axis_score.grid(row=9, column=1, padx=10)

        self.l2x_axis_score = tk.Label(self.stats, text="")
        self.l2x_axis_score.grid(row=9, column=2, padx=10)

        self.l1y_axis_score = tk.Label(self.stats, text="")
        self.l1y_axis_score.grid(row=10, column=1, padx=10)

        self.l2y_axis_score = tk.Label(self.stats, text="")
        self.l2y_axis_score.grid(row=10, column=2, padx=10)


        self.stat4 = tk.Label(self.stats, text="Parallel: ")
        self.stat4.grid(row=2, column=3, padx=10)
        self.canvas.bind("<Button-1>", self.on_canvas_click)
        self.canvas.bind("<B1-Motion>", self.on_canvas_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_canvas_release)
        # self.canvas.bind("<ButtonPress-1>", self.on_canvas_right_click)
        self.canvas.bind("<ButtonPress-1>", self.on_canvas_mouse_1_down)
    def on_canvas_mouse_1_down(self, event):
        """Handle mouse button 1 down events to start line selection."""
        x, y = event.x, event.y
        print(f"Mouse button 1 down at: ({x}, {y})")
        # Here you would implement logic to start selecting lines based on the click position.
        # For example, you could check if the click is near any detected line segments and start a selection process.
        try:
            # nearest line point
            distance1 = np.sqrt((x - self.line1.x1) ** 2 + (y - self.line1.y1) ** 2)
            distance2 = np.sqrt((x - self.line1.x2) ** 2 + (y - self.line1.y2) ** 2)
            distance3 = np.sqrt((x - self.line2.x1) ** 2 + (y - self.line2.y1) ** 2)
            distance4 = np.sqrt((x - self.line2.x2) ** 2 + (y - self.line2.y2) ** 2)
            min_distance = min(distance1, distance2, distance3, distance4)
            if min_distance < 10:  # threshold for selecting a point
                if min_distance == distance1:
                    self.selected_point = "line1_start"
                elif min_distance == distance2:
                    self.selected_point = "line1_end"
                elif min_distance == distance3:
                    self.selected_point = "line2_start"
                elif min_distance == distance4:
                    self.selected_point = "line2_end"
                    self.line2.x2, self.line2.y2 = x, y
        except Exception as e:
            print(f"[ERROR] An error occurred during drag: {e}")
            self.on_canvas_click(event)  # Call drag handler to update line position immediately

    def on_canvas_release(self, event):
        """Handle canvas release events to finalize line selection."""
        x, y = event.x, event.y
        print(f"Canvas released at: ({x}, {y})")
        # Here you would implement logic to finalize the selection of lines based on the release position.
        # For example, you could check if the release is near any detected line segments and finalize the selection.
        self.selected_point = None
        self.update_canvas()
        self.update_stats()
    def on_canvas_drag(self,  event):
        """Handle canvas drag events to select lines."""
        x, y = event.x, event.y
        clamp_x = max(0, min(self.canvas.winfo_width(), x))
        clamp_y = max(0, min(self.canvas.winfo_height(), y))
        print(f"Canvas dragged at: ({x}, {y})")
        if hasattr(self, 'selected_point'):
            if self.selected_point == "line1_start":
                self.line1.x1, self.line1.y1 = clamp_x, clamp_y
            elif self.selected_point == "line1_end":
                self.line1.x2, self.line1.y2 = clamp_x, clamp_y
            elif self.selected_point == "line2_start":
                self.line2.x1, self.line2.y1 = clamp_x, clamp_y
            elif self.selected_point == "line2_end":
                self.line2.x2, self.line2.y2 = clamp_x, clamp_y
        self.update_canvas()
        self.update_stats()
    def on_canvas_click(self, event):
        """Handle canvas click events to select lines."""
        x, y = event.x, event.y
        print(f"Canvas clicked at: ({x}, {y})")

        if self.line1 is None:
            self.line1 = Line(None, None,None,None)  # Placeholder for line selection
        if self.line1.x1 is None:
            self.line1.x1, self.line1.y1 = x, y

        elif self.line1.x2 is None:
            self.line1.x2, self.line1.y2 = x, y

        elif self.line2 is None:
            self.line2 = Line(None, None,None,None)  # Placeholder for line selection
        elif self.line2.x1 is None:
            self.line2.x1, self.line2.y1 = x, y

        elif self.line2.x2 is None:
            self.line2.x2, self.line2.y2 = x, y

        # self.update_canvas()
        # self.update_stats()
        # Here you would implement logic to select lines based on the click position.
        # For example, you could check if the click is near any detected line segments.

    def update_canvas(self):
        """Update the canvas to display the loaded image and detected lines."""
        # if self.image_pil:
        #     self.canvas.delete("all")
        #     self.tk_image = tk.PhotoImage(self.image_pil)
        #     self.canvas.create_image(0, 0, anchor=tk.NW, image=self.tk_image)
        #
        #     # Draw detected lines if available
        #     if self.lines is not None:
        #         for line in self.lines:
        #             x1, y1, x2, y2 = line
        #             self.canvas.create_line(x1, y1, x2, y2, fill="red", width=2)
        # else:
        self.canvas.delete("all")
        self.canvas.create_image(0, 0, anchor=tk.NW, image=tk.PhotoImage(width=800, height=400))  # Placeholder for empty canvas
            #draw line end points
        if self.line1 and self.line1.x1 is not None and self.line1.x2 is not None:
            self.canvas.create_oval(self.line1.x1-3, self.line1.y1-3, self.line1.x1+3, self.line1.y1+3, fill="blue")
            self.canvas.create_oval(self.line1.x2-3, self.line1.y2-3, self.line1.x2+3, self.line1.y2+3, fill="blue")
        if self.line2 and self.line2.x1 is not None and self.line2.x2 is not None:
            self.canvas.create_oval(self.line2.x1-3, self.line2.y1-3, self.line2.x1+3, self.line2.y1+3, fill="green")
            self.canvas.create_oval(self.line2.x2-3, self.line2.y2-3, self.line2.x2+3, self.line2.y2+3, fill="green")

        # Draw selected lines if available
        if self.line1 and self.line1.x1 is not None and self.line1.x2 is not None:
            self.canvas.create_line(self.line1.x1, self.line1.y1, self.line1.x2, self.line1.y2, fill="blue", width=3)
        if self.line2 and self.line2.x1 is not None and self.line2.x2 is not None:
            self.canvas.create_line(self.line2.x1, self.line2.y1, self.line2.x2, self.line2.y2, fill="green", width=3)

    def update_stats(self):
        print("Updating stats...")
        print(f"Line 1: {self.line1}, Line 2: {self.line2}")
        try:
            if self.line1 and self.line2:
                angle = self.line1.angle_with(self.line2)
                parallel = self.line1.parallel_with(self.line2)
                self.angle.config(text=f"{angle:.2f}°" if angle is not None else "N/A")
                self.collinear.config(text="Yes" if parallel else "No")
                self.l1angle.config(text=f"{self.line1.angle:.2f}°")
                self.l2angle.config(text=f"{self.line2.angle:.2f}°")
                self.l1length.config(text=f"{self.line1.length:.2f}")
                self.l2length.config(text=f"{self.line2.length:.2f}")
                self.l1unit.config(text=f"({self.line1.unit_vector[0]:.2f}, {self.line1.unit_vector[1]:.2f})")
                self.l2unit.config(text=f"({self.line2.unit_vector[0]:.2f}, {self.line2.unit_vector[1]:.2f})")
                dot_product = (self.line1.unit_vector[0] * self.line2.unit_vector[0] + self.line1.unit_vector[1] * self.line2.unit_vector[1])
                self.dot_product.config(text=f"{dot_product:.2f}")

                self.l1distance_start.config(text=f"{np.sqrt((self.line1.x1)**2 + (self.line1.y1)**2):.2f}, {np.sqrt((self.canvas.winfo_width() - self.line1.x1)**2 + (self.line1.y1)**2):.2f}, {np.sqrt((self.line1.x1)**2 + (self.canvas.winfo_height() - self.line1.y1)**2):.2f}, {np.sqrt((self.canvas.winfo_width() - self.line1.x1)**2 + (self.canvas.winfo_height() - self.line1.y1)**2):.2f}")
                self.l2distance_start.config(text=f"{np.sqrt((self.line2.x1)**2 + (self.line2.y1)**2):.2f}, {np.sqrt((self.canvas.winfo_width() - self.line2.x1)**2 + (self.line2.y1)**2):.2f}, {np.sqrt((self.line2.x1)**2 + (self.canvas.winfo_height() - self.line2.y1)**2):.2f}, {np.sqrt((self.canvas.winfo_width() - self.line2.x1)**2 + (self.canvas.winfo_height() - self.line2.y1)**2):.2f}")
                self.l1distance_end.config(text=f"{np.sqrt((self.line1.x2)**2 + (self.line1.y2)**2):.2f}, {np.sqrt((self.canvas.winfo_width() - self.line1.x2)**2 + (self.line1.y2)**2):.2f}, {np.sqrt((self.line1.x2)**2 + (self.canvas.winfo_height() - self.line1.y2)**2):.2f}, {np.sqrt((self.canvas.winfo_width() - self.line1.x2)**2 + (self.canvas.winfo_height() - self.line1.y2)**2):.2f}")
                self.l2distance_end.config(text=f"{np.sqrt((self.line2.x2)**2 + (self.line2.y2)**2):.2f}, {np.sqrt((self.canvas.winfo_width() - self.line2.x2)**2 + (self.line2.y2)**2):.2f}, {np.sqrt((self.line2.x2)**2 + (self.canvas.winfo_height() - self.line2.y2)**2):.2f}, {np.sqrt((self.canvas.winfo_width() - self.line2.x2)**2 + (self.canvas.winfo_height() - self.line2.y2)**2):.2f}")
                self.l1slope.config(text=f"{self.line1.slope:.2f}" if self.line1.slope != float('inf') else "Inf")
                self.l2slope.config(text=f"{self.line2.slope:.2f}" if self.line2.slope != float('inf') else "Inf")

            else:
                self.angle.config(text="")
                self.collinear.config(text="")
                self.l1angle.config(text="")
                self.l2angle.config(text="")
                self.l1length.config(text="")
                self.l2length.config(text="")
                self.l1unit.config(text="")
                self.l2unit.config(text="")
                self.l1slope.config(text="")
                self.l2slope.config(text="")
                self.dot_product.config(text="")
                self.l1distance_start.config(text="")
                self.l2distance_start.config(text="")
                self.l1distance_end.config(text="")
                self.l2distance_end.config(text="")

        except Exception as e:
            print(f"[ERROR] An error occurred while updating stats: {e}")



    def load_image(self):
        """Open a file dialog to select an image and load it."""
        self.image_path = filedialog.askopenfilename(title="Select an Image", filetypes=[("Image Files", "*.png;*.jpg;*.jpeg;*.bmp")])
        if self.image_path:
            try:
                self.image_pil = load_image(self.image_path)
                print(f"Loaded image: {self.image_path}")
            except FileNotFoundError:
                print(f"[ERROR] Image not found at: {self.image_path}")
            except Exception as e:
                print(f"[ERROR] An unexpected error occurred while loading the image: {e}")

    def process_image(self):
        """Process the loaded image to detect edges and lines."""
        if not self.image_pil:
            print("[ERROR] No image loaded. Please load an image first.")
            return

        try:
            edges = detect_edges(self.image_pil)
            print("Detected edges.")

            lines = detect_lines(edges, self.image_pil)
            print(f"Detected {len(lines) if lines is not None else 0} line segments.")

            selected_lines = select_lines(lines, self.image_pil)

            x_axis, y_axis = calculate_calibration(selected_lines)
            print(f"X Axis: {x_axis}, Y Axis: {y_axis}")

        except Exception as e:
            print(f"[ERROR] An unexpected error occurred during processing: {e}")



class Line(object):
    def __init__(self, x1, y1, x2, y2):
        self.x1 = x1
        self.y1 = y1
        self.x2 = x2
        self.y2 = y2

    def __repr__(self):
        return f"line({self.x1}, {self.y1}, {self.x2}, {self.y2})"

    @property
    def length(self):
        return np.sqrt((self.x2 - self.x1) ** 2 + (self.y2 - self.y1) ** 2)


    @property
    def angle(self):
        return np.arctan2(self.y2 - self.y1, self.x2 - self.x1) * 180 / np.pi


    @property
    def slope(self):
        if self.x2 - self.x1 == 0:
            return float('inf')  # vertical line
        return (self.y2 - self.y1) / (self.x2 - self.x1)



    def angle_with(self, other):
        """Calculate the angle between this line and another line in degrees."""
        dot_product = (self.x2 - self.x1) * (other.x2 - other.x1) + (self.y2 - self.y1) * (other.y2 - other.y1)
        mag_self = np.sqrt((self.x2 - self.x1) ** 2 + (self.y2 - self.y1) ** 2)
        mag_other = np.sqrt((other.x2 - other.x1) ** 2 + (other.y2 - other.y1) ** 2)
        if mag_self == 0 or mag_other == 0:
            return None  # One of the lines is a point
        cos_angle = dot_product / (mag_self * mag_other)
        cos_angle = np.clip(cos_angle, -1.0, 1.0)  # Clamp to avoid numerical issues
        angle_rad = np.arccos(cos_angle)
        return np.degrees(angle_rad)

    @property
    def unit_vector(self):
        """Return the unit vector of the line."""
        length = self.length
        if length == 0:
            return (0, 0)  # or raise an exception
        return ((self.x2 - self.x1) / length, (self.y2 - self.y1) / length)


    def parallel_with(self, other, tolerance=0.1):
        """Check if this line is parallel with another line within a given tolerance."""
        # Check if the slopes are equal (or both vertical)
        if self.slope == float('inf') and other.slope == float('inf'):
            return True
        elif self.slope == float('inf') or other.slope == float('inf'):
            return False
        else:
            return abs(self.slope - other.slope) < tolerance





def load_image(image_path):
    """Loads an image file using PIL."""
    return Image.open(image_path)

def detect_edges(image_pil):
    """Converts PIL image to OpenCV format, then applies Canny edge detection."""
    # Convert PIL Image to numpy array for OpenCV
    image_np = np.array(image_pil)
    # Convert to BGR color space if it's RGB (PIL usually loads as RGB)
    if image_np.ndim == 3 and image_np.shape[2] == 3:
        # Assuming PIL RGB -> OpenCV BGR for consistency
        image_cv = cv2.cvtColor(image_np, cv2.COLOR_RGB2BGR)
    else:
        image_cv = image_np

    # Convert to grayscale
    gray = cv2.cvtColor(image_cv, cv2.COLOR_BGR2GRAY)
    # Apply Canny edge detection
    edges = cv2.Canny(gray, 50, 200, apertureSize=3)
    # edges = cv2.dilate(edges, None)  # Optional: dilate edges to make them more pronounced
    return edges

def detect_lines(edges, image_pil=None):
    """Detects potential straight lines using the Hough Transform."""
    # HoughLinesP returns an array of lines: [[x1, y1, x2, y2], ...]
    lines = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=100, minLineLength=image_pil.width*0.4 if image_pil is not None else 100, maxLineGap=10)
    return lines

# Merge lines that are close to each other (within a certain threshold)
def merge_lines(lines, orientation='horizontal', threshold=10):
    """Should

    :param lines:
    :param orientation:
    :param threshold:
    :return:
    """


    if not lines:
        return []
    merged = []
    lines = sorted(lines, key=lambda l: l[1] if orientation == 'horizontal' else l[0])
    current_line = lines[0]
    for line in lines[1:]:
        if orientation == 'horizontal':
            if abs(line[1] - current_line[1]) < threshold:
                current_line = [min(current_line[0], line[0]), current_line[1], max(current_line[2], line[2]), current_line[3]]
            else:
                merged.append(current_line)
                current_line = line
        else:
            if abs(line[0] - current_line[0]) < threshold:
                current_line = [current_line[0], min(current_line[1], line[1]), current_line[2], max(current_line[3], line[3])]
            else:
                merged.append(current_line)
                current_line = line
    merged.append(current_line)
    return merged
def select_lines(lines, image_pil):
    """
    Placeholder for user interaction: allows the user to pick candidate lines 
    to define the axes. Needs a GUI implementation.
    """

    # show image with detected lines for user selection (show in pop-up window for placeholder)
    image_with_lines = np.array(image_pil.convert("RGB"))


    if lines is not None:
        # print(lines)
        for line in lines:
            print(line)
            x1, y1, x2, y2 = line
            cv2.line(image_with_lines, (x1, y1), (x2, y2), (255, 0, 0), 2, cv2.LINE_AA)

    horizontal_lines = [ line for line in sorted(lines, key=lambda l: l[1], reverse=True) if abs(line[1] - line[3]) < 10] if lines is not None else []
    vertical_lines = [ line for line in sorted(lines, key=lambda l: l[0]) if abs(line[0] - line[2]) < 10] if lines is not None else []


    # horizontal_lines = merge_lines(horizontal_lines, orientation='horizontal')
    # vertical_lines = merge_lines(vertical_lines, orientation='vertical')

    print(f"Detected {len(horizontal_lines)} horizontal lines and {len(vertical_lines)} vertical lines.")

    for line in horizontal_lines:
        x1, y1, x2, y2 = line
        cv2.line(image_with_lines, (x1, y1), (x2, y2), (0, 255, 0), 2, cv2.LINE_AA)
        break
    for line in vertical_lines:
        x1, y1, x2, y2 = line
        cv2.line(image_with_lines, (x1, y1), (x2, y2), (0, 0, 255), 2, cv2.LINE_AA)
        break

    cv2.imshow("Detected Lines", image_with_lines)
    cv2.waitKey(0)
    cv2.destroyAllWindows()
    return []  # Returns an empty list of selected line coordinates



    print("--- [INFO] User selection required. Placeholder function called. ---")
    print("Please implement a GUI here (e.g., using Tkinter/PyQt) to allow selection of lines.")



    return [] # Returns an empty list of selected line coordinates

def calculate_calibration(selected_lines):
    """
    Placeholder for calibration logic: calculates X and Y axis parameters 
    based on selected points/lines.
    """
    print("--- [INFO] Calibration logic placeholder called. ---")
    print("Implement the geometric calculations here to derive X and Y axis parameters.")
    return None, None # Returns placeholder None values

def process_image_and_calibrate(image_path):
    """Main workflow function for image feature detection and calibration."""
    try:
        image_pil = load_image(image_path)
        print(f"Loaded image: {image_path}")

        edges = detect_edges(image_pil)
        print("Detected edges.")

        lines = detect_lines(edges, image_pil)
        print(f"Detected {len(lines) if lines is not None else 0} line segments.")

        selected_lines = select_lines(lines, image_pil)

        x_axis, y_axis = calculate_calibration(selected_lines)

        return x_axis, y_axis

    except FileNotFoundError:
        print(f"[ERROR] Image not found at: {image_path}")
        return None, None
    except Exception as e:
        print(f"[ERROR] An unexpected error occurred: {e}")
        return None, None





if __name__ == "__main__":
    # Example usage
    # image_path = r"C:\python_projects\img2data\img.png"  # Replace with your image path
    # x_axis, y_axis = process_image_and_calibrate(image_path)
    # print(f"X Axis: {x_axis}, Y Axis: {y_axis}")

    app = LineTestBed()
    app.mainloop()
