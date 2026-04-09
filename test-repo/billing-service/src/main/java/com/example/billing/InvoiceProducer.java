package com.example.billing;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.apache.kafka.clients.producer.KafkaProducer;
import org.apache.kafka.clients.producer.ProducerRecord;
import org.apache.kafka.common.serialization.StringSerializer;

import java.util.Properties;

public class InvoiceProducer {

    private final KafkaProducer<String, String> producer;
    private final ObjectMapper objectMapper = new ObjectMapper();

    public InvoiceProducer(String bootstrapServers) {
        Properties props = new Properties();
        props.put("bootstrap.servers", bootstrapServers);
        props.put("key.serializer", StringSerializer.class.getName());
        props.put("value.serializer", StringSerializer.class.getName());
        this.producer = new KafkaProducer<>(props);
    }

    public void sendInvoice(InvoiceEvent event) throws Exception {
        String json = objectMapper.writeValueAsString(event);
        producer.send(new ProducerRecord<>("financial-events", event.getInvoiceId(), json));
    }

    public void close() {
        producer.close();
    }
}
