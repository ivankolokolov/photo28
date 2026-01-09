"""Сервис умного кадрирования с определением лиц."""
import io
import logging
from dataclasses import dataclass
from typing import Optional, List, Tuple
import json

logger = logging.getLogger(__name__)

# Ленивая загрузка тяжёлых библиотек
cv2 = None
np = None


def _load_cv2():
    """Ленивая загрузка OpenCV."""
    global cv2, np
    if cv2 is None:
        try:
            import cv2 as _cv2
            import numpy as _np
            cv2 = _cv2
            np = _np
            logger.info("OpenCV загружен успешно")
        except ImportError:
            logger.warning("OpenCV не установлен. Умный кроп недоступен.")
            return False
    return True


@dataclass
class CropResult:
    """Результат анализа кропа."""
    x: int  # Координата X левого верхнего угла
    y: int  # Координата Y левого верхнего угла
    width: int  # Ширина области кропа
    height: int  # Высота области кропа
    confidence: float  # Уверенность в кропе (0-1)
    faces_found: int  # Количество найденных лиц
    method: str  # Метод: "face", "saliency", "center"
    
    def to_dict(self) -> dict:
        """Преобразует в словарь для JSON."""
        return {
            "x": self.x,
            "y": self.y,
            "width": self.width,
            "height": self.height,
            "confidence": round(self.confidence, 2),
            "faces_found": self.faces_found,
            "method": self.method,
        }
    
    def to_json(self) -> str:
        """Сериализует в JSON."""
        return json.dumps(self.to_dict())


class SmartCropService:
    """Сервис умного кадрирования фотографий."""
    
    # Соотношения сторон для форматов (ширина / высота)
    FORMAT_RATIOS = {
        "polaroid_standard": 0.76,   # 7.6 / 10
        "polaroid_wide": 0.85,       # ~шире
        "instax": 0.628,             # 5.4 / 8.6
        "classic": 0.667,            # 10 / 15
    }
    
    def __init__(self, face_priority: int = 80):
        """
        Args:
            face_priority: Приоритет лиц (0-100). 100 = всегда по лицу.
        """
        self.face_priority = face_priority / 100.0
        self._face_cascade = None
    
    def _get_face_cascade(self):
        """Ленивая загрузка каскада для определения лиц."""
        if not _load_cv2():
            return None
        
        if self._face_cascade is None:
            cascade_path = cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
            self._face_cascade = cv2.CascadeClassifier(cascade_path)
        
        return self._face_cascade
    
    def analyze_photo(
        self,
        image_bytes: bytes,
        photo_format: str = "polaroid_standard",
    ) -> CropResult:
        """
        Анализирует фото и определяет оптимальную область кропа.
        
        Args:
            image_bytes: Байты изображения
            photo_format: Формат фото (polaroid_standard, instax, classic)
        
        Returns:
            CropResult с координатами и уверенностью
        """
        if not _load_cv2():
            # Если OpenCV недоступен — возвращаем центральный кроп
            return self._fallback_center_crop(image_bytes, photo_format)
        
        try:
            # Декодируем изображение
            nparr = np.frombuffer(image_bytes, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            
            if img is None:
                logger.error("Не удалось декодировать изображение")
                return self._fallback_center_crop(image_bytes, photo_format)
            
            img_height, img_width = img.shape[:2]
            target_ratio = self.FORMAT_RATIOS.get(photo_format, 0.76)
            
            # 1. Пробуем найти лица
            faces = self._detect_faces(img)
            
            if faces and self.face_priority > 0:
                crop = self._crop_around_faces(
                    img_width, img_height, faces, target_ratio
                )
                return crop
            
            # 2. Если нет лиц — saliency detection
            saliency_crop = self._saliency_crop(img, target_ratio)
            if saliency_crop:
                return saliency_crop
            
            # 3. Fallback — центральный кроп
            return self._center_crop(img_width, img_height, target_ratio)
            
        except Exception as e:
            logger.error(f"Ошибка анализа фото: {e}")
            return self._fallback_center_crop(image_bytes, photo_format)
    
    def _detect_faces(self, img) -> List[Tuple[int, int, int, int]]:
        """Определяет лица на изображении."""
        cascade = self._get_face_cascade()
        if cascade is None:
            return []
        
        # Конвертируем в grayscale
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        
        # Определяем лица
        faces = cascade.detectMultiScale(
            gray,
            scaleFactor=1.1,
            minNeighbors=5,
            minSize=(30, 30),
            flags=cv2.CASCADE_SCALE_IMAGE
        )
        
        # Преобразуем в список кортежей
        return [(x, y, w, h) for (x, y, w, h) in faces]
    
    def _crop_around_faces(
        self,
        img_width: int,
        img_height: int,
        faces: List[Tuple[int, int, int, int]],
        target_ratio: float,
    ) -> CropResult:
        """Создаёт кроп вокруг лиц."""
        # Находим общий bounding box всех лиц
        min_x = min(f[0] for f in faces)
        min_y = min(f[1] for f in faces)
        max_x = max(f[0] + f[2] for f in faces)
        max_y = max(f[1] + f[3] for f in faces)
        
        # Центр всех лиц
        faces_center_x = (min_x + max_x) // 2
        faces_center_y = (min_y + max_y) // 2
        
        # Вычисляем размер кропа с учётом соотношения сторон
        crop_width, crop_height = self._calculate_crop_size(
            img_width, img_height, target_ratio
        )
        
        # Центрируем кроп на лицах
        crop_x = faces_center_x - crop_width // 2
        crop_y = faces_center_y - crop_height // 2
        
        # Корректируем, чтобы не выходить за границы
        crop_x = max(0, min(crop_x, img_width - crop_width))
        crop_y = max(0, min(crop_y, img_height - crop_height))
        
        # Уверенность зависит от того, насколько хорошо лица попадают в кроп
        faces_in_crop = self._count_faces_in_crop(
            faces, crop_x, crop_y, crop_width, crop_height
        )
        confidence = min(1.0, faces_in_crop / len(faces)) * 0.9 + 0.1
        
        # Если одно лицо и оно по центру — высокая уверенность
        if len(faces) == 1:
            confidence = 0.95
        
        return CropResult(
            x=int(crop_x),
            y=int(crop_y),
            width=int(crop_width),
            height=int(crop_height),
            confidence=confidence,
            faces_found=len(faces),
            method="face"
        )
    
    def _saliency_crop(
        self,
        img,
        target_ratio: float,
    ) -> Optional[CropResult]:
        """Определяет важные области методом saliency detection."""
        try:
            # Создаём saliency detector
            saliency = cv2.saliency.StaticSaliencyFineGrained_create()
            
            # Вычисляем saliency map
            success, saliency_map = saliency.computeSaliency(img)
            
            if not success:
                return None
            
            # Находим точку с максимальной "важностью"
            saliency_map = (saliency_map * 255).astype(np.uint8)
            
            # Применяем blur для сглаживания
            saliency_map = cv2.GaussianBlur(saliency_map, (51, 51), 0)
            
            # Находим максимум
            _, _, _, max_loc = cv2.minMaxLoc(saliency_map)
            center_x, center_y = max_loc
            
            img_height, img_width = img.shape[:2]
            crop_width, crop_height = self._calculate_crop_size(
                img_width, img_height, target_ratio
            )
            
            # Центрируем на точке интереса
            crop_x = center_x - crop_width // 2
            crop_y = center_y - crop_height // 2
            
            # Корректируем границы
            crop_x = max(0, min(crop_x, img_width - crop_width))
            crop_y = max(0, min(crop_y, img_height - crop_height))
            
            return CropResult(
                x=int(crop_x),
                y=int(crop_y),
                width=int(crop_width),
                height=int(crop_height),
                confidence=0.7,  # Средняя уверенность для saliency
                faces_found=0,
                method="saliency"
            )
            
        except Exception as e:
            logger.warning(f"Saliency detection не удался: {e}")
            return None
    
    def _center_crop(
        self,
        img_width: int,
        img_height: int,
        target_ratio: float,
    ) -> CropResult:
        """Центральный кроп (fallback)."""
        crop_width, crop_height = self._calculate_crop_size(
            img_width, img_height, target_ratio
        )
        
        crop_x = (img_width - crop_width) // 2
        crop_y = (img_height - crop_height) // 2
        
        return CropResult(
            x=int(crop_x),
            y=int(crop_y),
            width=int(crop_width),
            height=int(crop_height),
            confidence=0.5,  # Низкая уверенность для центра
            faces_found=0,
            method="center"
        )
    
    def _calculate_crop_size(
        self,
        img_width: int,
        img_height: int,
        target_ratio: float,
    ) -> Tuple[int, int]:
        """Вычисляет размер области кропа с сохранением соотношения."""
        img_ratio = img_width / img_height
        
        if img_ratio > target_ratio:
            # Изображение шире — ограничиваем по высоте
            crop_height = img_height
            crop_width = int(crop_height * target_ratio)
        else:
            # Изображение выше — ограничиваем по ширине
            crop_width = img_width
            crop_height = int(crop_width / target_ratio)
        
        return crop_width, crop_height
    
    def _count_faces_in_crop(
        self,
        faces: List[Tuple[int, int, int, int]],
        crop_x: int,
        crop_y: int,
        crop_width: int,
        crop_height: int,
    ) -> int:
        """Подсчитывает лица, попадающие в область кропа."""
        count = 0
        for (fx, fy, fw, fh) in faces:
            face_center_x = fx + fw // 2
            face_center_y = fy + fh // 2
            
            if (crop_x <= face_center_x <= crop_x + crop_width and
                crop_y <= face_center_y <= crop_y + crop_height):
                count += 1
        
        return count
    
    def _fallback_center_crop(
        self,
        image_bytes: bytes,
        photo_format: str,
    ) -> CropResult:
        """Fallback кроп без OpenCV (по центру с примерными размерами)."""
        # Пробуем определить размер через PIL
        try:
            from PIL import Image
            img = Image.open(io.BytesIO(image_bytes))
            img_width, img_height = img.size
        except Exception:
            # Совсем fallback — предполагаем стандартное фото
            img_width, img_height = 1920, 1080
        
        target_ratio = self.FORMAT_RATIOS.get(photo_format, 0.76)
        crop_width, crop_height = self._calculate_crop_size(
            img_width, img_height, target_ratio
        )
        
        return CropResult(
            x=(img_width - crop_width) // 2,
            y=(img_height - crop_height) // 2,
            width=crop_width,
            height=crop_height,
            confidence=0.5,
            faces_found=0,
            method="center"
        )
    
    @staticmethod
    def is_available() -> bool:
        """Проверяет, доступен ли OpenCV."""
        return _load_cv2()


# Глобальный экземпляр (создаётся лениво)
_smart_crop_service: Optional[SmartCropService] = None


def get_smart_crop_service(face_priority: int = 80) -> SmartCropService:
    """Получает экземпляр SmartCropService."""
    global _smart_crop_service
    if _smart_crop_service is None:
        _smart_crop_service = SmartCropService(face_priority)
    return _smart_crop_service
