CREATE DATABASE IF NOT EXISTS hospital_queue
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

USE hospital_queue;

CREATE TABLE IF NOT EXISTS users (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(254) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    role ENUM('patient', 'staff') NOT NULL DEFAULT 'patient',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS schedules (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    title VARCHAR(120) NOT NULL,
    doctor_name VARCHAR(100) NOT NULL,
    schedule_date DATE NOT NULL,
    start_time TIME NOT NULL,
    end_time TIME NOT NULL,
    capacity SMALLINT UNSIGNED NOT NULL,
    created_by BIGINT UNSIGNED NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_schedules_creator FOREIGN KEY (created_by) REFERENCES users(id),
    INDEX idx_schedules_date_time (schedule_date, start_time)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS appointments (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    schedule_id BIGINT UNSIGNED NOT NULL,
    patient_id BIGINT UNSIGNED NOT NULL,
    status ENUM('waiting', 'serving', 'completed', 'cancelled') NOT NULL DEFAULT 'waiting',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_appointments_schedule FOREIGN KEY (schedule_id) REFERENCES schedules(id),
    CONSTRAINT fk_appointments_patient FOREIGN KEY (patient_id) REFERENCES users(id),
    INDEX idx_schedule_patient (schedule_id, patient_id, status),
    INDEX idx_queue_order (schedule_id, status, created_at, id)
) ENGINE=InnoDB;

-- Create a staff user by registering a patient account, then promote it:
-- UPDATE users SET role = 'staff' WHERE email = 'staff@your-hospital.example';
