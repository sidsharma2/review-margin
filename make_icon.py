"""Draws assets/icon.png (1024px): a paper page beside a ruled notes area."""
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QGuiApplication, QImage, QPainter, QPen

app = QGuiApplication([])
S = 1024
img = QImage(S, S, QImage.Format_ARGB32)
img.fill(Qt.transparent)
p = QPainter(img)
p.setRenderHint(QPainter.Antialiasing)
p.setPen(Qt.NoPen)
p.setBrush(QColor("#3b6fe0"))
p.drawRoundedRect(QRectF(80, 80, 864, 864), 190, 190)
# landscape sheet
p.setBrush(QColor("#ffffff"))
sheet = QRectF(170, 270, 684, 500)
p.drawRoundedRect(sheet, 28, 28)
# paper text blocks on the left
p.setBrush(QColor("#9aa7bf"))
for i, w in enumerate([270, 300, 300, 240, 300, 300, 200]):
    p.drawRoundedRect(QRectF(215, 320 + i * 58, w, 22), 11, 11)
# divider + ruled lines on the right
p.setPen(QPen(QColor("#d0d6e2"), 6))
p.drawLine(560, 290, 560, 750)
p.setPen(QPen(QColor("#c6cfe0"), 5))
for i in range(6):
    y = 345 + i * 66
    p.drawLine(595, y, 815, y)
# pen stroke
p.setPen(QPen(QColor("#f2a33a"), 18, Qt.SolidLine, Qt.RoundCap))
p.drawLine(600, 470, 700, 430)
p.end()
img.save("assets/icon.png")
print("assets/icon.png")
