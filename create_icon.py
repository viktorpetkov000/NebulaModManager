from PIL import Image, ImageDraw, ImageFilter
import os

def create_nebula_icon():
    size = 256
    # Deep space background
    img = Image.new('RGBA', (size, size), (11, 15, 25, 255)) 
    draw = ImageDraw.Draw(img)
    
    # Draw "nebula" clouds using theme colors
    draw.ellipse([20, 20, 180, 180], fill=(99, 102, 241, 150))  # Indigo
    draw.ellipse([80, 80, 240, 240], fill=(217, 70, 239, 150))  # Purple/Pink
    draw.ellipse([50, 120, 200, 250], fill=(49, 46, 129, 200))  # Deep Blue
    
    # Blur the clouds to make them look gaseous
    img = img.filter(ImageFilter.GaussianBlur(18))
    draw = ImageDraw.Draw(img)
    
    # Add scattered stars
    stars = [(40, 50), (200, 40), (220, 180), (60, 200), (130, 30), (150, 220), (90, 210), (30, 120)]
    for sx, sy in stars:
        draw.ellipse([sx, sy, sx+4, sy+4], fill=(255, 255, 255, 200))
        
    # Draw a sleek, geometric 'N'
    n_color = (248, 250, 252, 255) # Silver/White
    draw.polygon([
        (80, 180), (80, 70), (110, 70), (160, 150), 
        (160, 70), (190, 70), (190, 180), (160, 180), 
        (110, 100), (110, 180)
    ], fill=n_color)

    # Save as a multi-size Windows Icon
    img.save('icon.ico', format='ICO', sizes=[(256, 256), (128, 128), (64, 64), (32, 32), (16, 16)])
    print("Nebula icon.ico generated successfully!")

if __name__ == "__main__":
    create_nebula_icon()