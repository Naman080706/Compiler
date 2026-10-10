#include <stdio.h>

int main(void) {
    double celsius = -10.0;
    double fahrenheit;
    double step = 10.0;
    printf("Celsius  Fahrenheit\n");
    while (celsius <= 40.0) {
        fahrenheit = celsius * 9.0 / 5.0 + 32.0;
        printf("%f  %f\n", celsius, fahrenheit);
        celsius += step;
    }
    printf("Table finished\n");
    return 0;
}
