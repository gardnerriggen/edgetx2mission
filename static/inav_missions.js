document.addEventListener('DOMContentLoaded', function() {
    const missionForm = document.getElementById('missionForm');
    const unitToggle = document.getElementById('unitToggle');
    const resetBtn = document.getElementById('resetBtn');

    // Show error modal automatically if it exists in the DOM
    const errorModalEl = document.getElementById('errorModal');
    if (errorModalEl) {
        const errorModal = new bootstrap.Modal(errorModalEl);
        errorModal.show();
    }

    // 1. Form Submission (Spinner + Success Modal)
    missionForm.onsubmit = function() {
        const overlay = document.getElementById('loadingOverlay');
        const missionInput = document.getElementById('mission_name').value;
        const displayFilename = document.getElementById('display_filename');
        
        let finalName = missionInput || "converted_mission";
        if (!finalName.toLowerCase().endsWith('.mission')) {
            finalName += '.mission';
        }
        displayFilename.innerText = finalName;

        overlay.style.display = 'flex';

        setTimeout(() => {
            overlay.style.display = 'none';
            var successModal = new bootstrap.Modal(document.getElementById('successModal'));
            successModal.show();
        }, 2500);
    };

    // 2. Unit Toggle Logic (With Value Conversion)
    window.toggleUnits = function() {
        const isImperial = unitToggle.checked;
        const unitDistLabels = document.querySelectorAll('.unit-dist');
        const unitSpeedLabels = document.querySelectorAll('.unit-speed');
        const systemInput = document.getElementById('unit_system');
        
        const altInput = document.getElementById('custom_alt');
        const speedInput = document.getElementById('cruise_speed');
        const spacingInput = document.getElementById('spacing');

        const mToFt = 3.28084;
        const kmhToMph = 0.621371;

        if (isImperial) {
            systemInput.value = 'imperial';
            unitDistLabels.forEach(el => el.innerText = 'ft');
            unitSpeedLabels.forEach(el => el.innerText = 'mph');

            if (altInput.value) altInput.value = (parseFloat(altInput.value) * mToFt).toFixed(0);
            if (speedInput.value) speedInput.value = (parseFloat(speedInput.value) * kmhToMph).toFixed(1);
            if (spacingInput.value) spacingInput.value = (parseFloat(spacingInput.value) * mToFt).toFixed(0);
        } else {
            systemInput.value = 'metric';
            unitDistLabels.forEach(el => el.innerText = 'm');
            unitSpeedLabels.forEach(el => el.innerText = 'km/h');

            if (altInput.value) altInput.value = (parseFloat(altInput.value) / mToFt).toFixed(0);
            if (speedInput.value) speedInput.value = (parseFloat(speedInput.value) / kmhToMph).toFixed(1);
            if (spacingInput.value) spacingInput.value = (parseFloat(spacingInput.value) / mToFt).toFixed(0);
        }
    };

    // 3. Reset Logic
    window.resetForm = function() {
        missionForm.reset();
        unitToggle.checked = false;
        
        document.querySelectorAll('.unit-dist').forEach(el => el.innerText = 'm');
        document.querySelectorAll('.unit-speed').forEach(el => el.innerText = 'km/h');
        
        document.getElementById('unit_system').value = 'metric';
        document.getElementById("mission_name").value = DEFAULT_MISSION_NAME;
        document.getElementById("cruise_speed").value = "25.0";
        document.getElementById("spacing").value = "100";
        document.getElementById("custom_alt").value = "";
    };

    resetBtn.addEventListener('click', resetForm);
});
