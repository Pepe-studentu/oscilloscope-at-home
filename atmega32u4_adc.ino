/*
 * ATmega32U4
 * ADC: free-running, 8-bit (ADLAR), ~38.5 ksps
 */

static void setClock16MHz() {
    cli();
    CLKPR = (1 << CLKPCE);
    CLKPR = 0x00;
    sei();
}

static void setupADC() {
    ADMUX  = (1 << REFS0)   // AVcc reference
           | (1 << ADLAR)   // Left-adjust: ADCH holds top 8 bits
           | 0x00;          // MUX = ADC0 pin

    ADCSRB = 0x00;          // Auto-trigger source: free running

    ADCSRA = (1 << ADEN)
           | (1 << ADSC)
           | (1 << ADATE)
           | 0b101;          // Prescaler /32 → 500 kHz ADC clock → ~38.5 ksps

    while (!(ADCSRA & (1 << ADIF)));  // Wait for first conversion to complete
    ADCSRA |= (1 << ADIF);   
    }



void setup() {
    setClock16MHz();
    Serial.begin(384610); // 1 bit start, 8 bits sample, 1 bit end
    delay(1000);
    setupADC();
}

void loop() {
    while (!(ADCSRA & (1 << ADIF)));
    ADCSRA |= (1 << ADIF);  // pulse the ADIF flag
    uint8_t val = ADCH;
    Serial.write(val);
}