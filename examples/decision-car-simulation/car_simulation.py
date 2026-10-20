import pygame
import math
import sys

# Initialize Pygame
pygame.init()

# Simulation Constants
WIDTH, HEIGHT = 1000, 400
FPS = 60
WHITE = (255, 255, 255)
GREY = (50, 50, 50)
RED = (220, 50, 50)
BLUE = (50, 120, 240)
YELLOW = (240, 240, 50)
BLACK = (0, 0, 0)

screen = pygame.display.set_available_cameras if False else pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("Car Animation & Decision Model Test")
clock = pygame.time.Clock()

# --- DECISION MODEL (Intelligent Driver Model parameters) ---
V0 = 40.0   # Desired velocity (pixels/second)
T = 1.5     # Safe time headway (seconds)
A_MAX = 2.0 # Maximum acceleration (pixels/second^2)
B_MAX = 3.0 # Comfortable deceleration (pixels/second^2)
S0 = 30.0   # Minimum jam distance (pixels)
DELTA = 4   # Acceleration exponent

class Car:
    def __init__(self, x, y, color, speed, is_lead=False):
        self.x = x
        self.y = y
        self.width = 50
        self.height = 25
        self.color = color
        self.v = speed  # Current velocity
        self.a = 0.0    # Current acceleration
        self.is_lead = is_lead
        self.decision_status = "Cruising"

    def update_decision(self, lead_car, dt):
        """
        Calculates the acceleration decision using IDM formulation.
        """
        if self.is_lead:
            # Lead car follows independent test behavior (e.g., unexpected braking)
            return

        # Distance to lead car front-to-back
        s = (lead_car.x) - (self.x + self.width)
        dv = self.v - lead_car.v  # Approach rate

        # Handle edge cases where cars overlap or cross
        if s <= 0:
            s = 0.1

        # IDM Decision Formula
        # Desired minimum gap dynamic term
        s_star = S0 + max(0.0, (self.v * T) + ((self.v * dv) / (2 * math.sqrt(A_MAX * B_MAX))))
        
        # Calculate resulting acceleration choice
        self.a = A_MAX * (1.0 - (self.v / V0)**DELTA - (s_star / s)**2)
        
        # State classification for display text
        if self.a < -1.5:
            self.decision_status = "BRAKING (Danger)"
        elif self.a < 0:
            self.decision_status = "Slowing Down"
        else:
            self.decision_status = "Accelerating"

    def move(self, dt):
        # Update physics
        self.v += self.a * dt
        if self.v < 0: 
            self.v = 0 # Prevent moving backwards
        self.x += self.v * dt

    def draw(self, surface):
        # Draw car chassis
        pygame.draw.rect(surface, self.color, (int(self.x), int(self.y), self.width, self.height))
        # Draw wheels
        pygame.draw.circle(surface, BLACK, (int(self.x + 10), int(self.y + self.height)), 6)
        pygame.draw.circle(surface, BLACK, (int(self.x + self.width - 10), int(self.y + self.height)), 6)
        # Draw windshield to signify direction (facing right)
        pygame.draw.rect(surface, WHITE, (int(self.x + self.width - 12), int(self.y + 3), 8, 8))

# Instantiate vehicles
# Lead car starts ahead; Follower car starts at x=50 with speed 35
lead_car = Car(600, 200, RED, 25.0, is_lead=True)
follower_car = Car(50, 200, BLUE, 35.0, is_lead=False)

# UI Font Setup
font = pygame.font.SysFont("Arial", 16)

running = True
simulation_time = 0.0

while running:
    dt = clock.tick(FPS) / 1000.0  # Normalize delta time to seconds
    simulation_time += dt

    # Handle Events
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False
        # Reset simulation using 'R' key
        if event.type == pygame.KEYDOWN and event.key == pygame.K_r:
            lead_car = Car(600, 200, RED, 25.0, is_lead=True)
            follower_car = Car(50, 200, BLUE, 35.0, is_lead=False)
            simulation_time = 0.0

    # --- SCRIPTED TEST SCENARIO ---
    # At 3 seconds, the lead car encounters an emergency obstacle and aggressively brakes
    if simulation_time > 3.0 and simulation_time < 5.5:
        lead_car.a = -4.5
        lead_car.decision_status = "Emergency Stopping!"
    elif simulation_time >= 5.5:
        lead_car.a = 0
        lead_car.v = 0
        lead_car.decision_status = "Stopped"
    else:
        lead_car.decision_status = "Driving standard speed"

    # --- UPDATE AGENT DECISION MODEL ---
    follower_car.update_decision(lead_car, dt)

    # --- APPLY PHYSICS ---
    lead_car.move(dt)
    follower_car.move(dt)

    # --- RENDER WEB ANIMATION SCENE ---
    screen.fill(WHITE)
    
    # Draw Road Environment
    pygame.draw.rect(screen, GREY, (0, 180, WIDTH, 70))
    # Dashed center lane line
    for x in range(0, WIDTH, 40):
        pygame.draw.line(screen, YELLOW, (x, 215), (x + 20, 215), 2)

    # Draw Vehicles
    lead_car.draw(screen)
    follower_car.draw(screen)

    # Render On-screen Telemetry Overlay
    time_txt = font.render(f"Simulation Time: {simulation_time:.2f}s (Press 'R' to Reset)", True, BLACK)
    screen.blit(time_txt, (20, 20))

    # Follower Car Stats
    f_txt = font.render(f"Blue Car Model Decision: {follower_car.decision_status}", True, BLUE)
    f_speed = font.render(f"Velocity: {follower_car.v:.1f} px/s | Accel: {follower_car.a:.2f} px/s²", True, BLUE)
    screen.blit(f_txt, (20, 60))
    screen.blit(f_speed, (20, 80))

    # Lead Car Stats
    l_txt = font.render(f"Red Car State: {lead_car.decision_status}", True, RED)
    l_speed = font.render(f"Velocity: {lead_car.v:.1f} px/s", True, RED)
    screen.blit(l_txt, (600, 60))
    screen.blit(l_speed, (600, 80))

    # Check for crash condition
    if follower_car.x + follower_car.width >= lead_car.x:
        crash_txt = pygame.font.SysFont("Arial", 36, bold=True).render("CRASH DETECTED: Decision Model Failure!", True, RED)
        screen.blit(crash_txt, (WIDTH // 2 - 250, HEIGHT - 80))

    pygame.display.flip()

pygame.quit()
sys.exit()