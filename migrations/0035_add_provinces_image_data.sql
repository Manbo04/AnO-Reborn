-- Province custom banner images (base64 JPEG in image_data, like country flags)
ALTER TABLE provinces ADD COLUMN IF NOT EXISTS image_data TEXT;
