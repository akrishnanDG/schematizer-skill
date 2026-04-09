package com.example.legacy;

import org.apache.avro.Schema;
import org.apache.avro.generic.GenericData;
import org.apache.avro.generic.GenericDatumWriter;
import org.apache.avro.generic.GenericRecord;
import org.apache.avro.io.BinaryEncoder;
import org.apache.avro.io.EncoderFactory;
import org.apache.kafka.clients.producer.KafkaProducer;
import org.apache.kafka.clients.producer.ProducerRecord;
import org.apache.kafka.common.serialization.ByteArraySerializer;
import org.apache.kafka.common.serialization.StringSerializer;

import java.io.ByteArrayOutputStream;
import java.util.Properties;

/**
 * Custom Avro serialization WITHOUT Schema Registry — Category E.
 */
public class CustomerProducer {

    private static final String SCHEMA_JSON = "{"
        + "\"type\": \"record\","
        + "\"name\": \"Customer\","
        + "\"namespace\": \"com.example.legacy\","
        + "\"fields\": ["
        + "  {\"name\": \"customer_id\", \"type\": \"string\"},"
        + "  {\"name\": \"first_name\", \"type\": \"string\"},"
        + "  {\"name\": \"last_name\", \"type\": \"string\"},"
        + "  {\"name\": \"email\", \"type\": \"string\"},"
        + "  {\"name\": \"phone_number\", \"type\": \"string\"},"
        + "  {\"name\": \"date_of_birth\", \"type\": \"string\"},"
        + "  {\"name\": \"ssn\", \"type\": \"string\"},"
        + "  {\"name\": \"address\", \"type\": \"string\"}"
        + "]}";

    private final Schema schema = new Schema.Parser().parse(SCHEMA_JSON);
    private final KafkaProducer<String, byte[]> producer;

    public CustomerProducer(String bootstrapServers) {
        Properties props = new Properties();
        props.put("bootstrap.servers", bootstrapServers);
        props.put("key.serializer", StringSerializer.class.getName());
        props.put("value.serializer", ByteArraySerializer.class.getName());
        this.producer = new KafkaProducer<>(props);
    }

    public void sendCustomer(String customerId, String firstName, String lastName,
                              String email, String phone, String dob, String ssn, String address)
            throws Exception {
        GenericRecord record = new GenericData.Record(schema);
        record.put("customer_id", customerId);
        record.put("first_name", firstName);
        record.put("last_name", lastName);
        record.put("email", email);
        record.put("phone_number", phone);
        record.put("date_of_birth", dob);
        record.put("ssn", ssn);
        record.put("address", address);

        ByteArrayOutputStream out = new ByteArrayOutputStream();
        BinaryEncoder encoder = EncoderFactory.get().binaryEncoder(out, null);
        GenericDatumWriter<GenericRecord> writer = new GenericDatumWriter<>(schema);
        writer.write(record, encoder);
        encoder.flush();

        producer.send(new ProducerRecord<>("customer-profiles", customerId, out.toByteArray()));
    }

    public void close() {
        producer.close();
    }
}
